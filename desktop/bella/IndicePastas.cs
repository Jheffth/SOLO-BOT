using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;

namespace Bella {
    public sealed class ResultadoPastas {
        public string[] Caminhos=new string[0];
        public bool Completa, Exata, Mais, EmAndamento;
    }
    // Somente diretórios: um trabalhador, sem rede, conteúdo de arquivos ou watchers.
    public sealed class IndicePastas : IDisposable {
        readonly object trava=new object();
        readonly Func<IEnumerable<string>> raizes;
        readonly Func<string,IEnumerable<string>> listar;
        readonly Func<DateTime> agora;
        readonly int limite, pausaMs, esperaMs;
        readonly TimeSpan validade, orcamento;
        readonly Dictionary<string,List<string>> nomes=new Dictionary<string,List<string>>(StringComparer.Ordinal);
        readonly Dictionary<string,string> compactos=new Dictionary<string,string>(StringComparer.Ordinal);
        volatile bool encerrado;
        bool trabalhando, pronto, parcial;
        int quantidade,consultadas;
        DateTime atualizado;
        public IndicePastas(Func<IEnumerable<string>> roots,Func<string,IEnumerable<string>> enumerate=null,
            Func<DateTime> clock=null,int maxDirectories=60000,int pauseMilliseconds=30,int waitMilliseconds=1200,
            TimeSpan? refresh=null,TimeSpan? budget=null) {
            raizes=roots; listar=enumerate ?? Directory.EnumerateDirectories; agora=clock ?? (()=>DateTime.UtcNow);
            limite=Math.Max(1,maxDirectories); pausaMs=Math.Max(0,pauseMilliseconds); esperaMs=Math.Max(0,waitMilliseconds);
            validade=refresh ?? TimeSpan.FromMinutes(15); orcamento=budget ?? TimeSpan.FromSeconds(90);
        }
        public bool Encerrado { get { return encerrado; } }
        public int Consultadas { get { lock(trava) return consultadas; } }
        public int Quantidade { get { lock(trava) return quantidade; } }
        public bool Trabalhando { get { lock(trava) return trabalhando; } }
        public void Iniciar() {
            lock(trava) {
                if(encerrado || trabalhando || (pronto && agora()-atualizado<validade)) return;
                trabalhando=true; pronto=false; parcial=false; quantidade=0; consultadas=0; nomes.Clear(); compactos.Clear();
                var thread=new Thread(Construir) {IsBackground=true,Name="BellaIndicePastas",Priority=ThreadPriority.BelowNormal};
                thread.Start();
            }
        }
        public ResultadoPastas Buscar(string termo,string lugar=null) {
            termo=Arquivos.Dobrar((termo ?? "").Trim());
            if(termo.Length==0 || encerrado) return new ResultadoPastas();
            if(lugar!=null) lugar=Arquivos.Canonico(lugar);
            Iniciar();
            var espera=Stopwatch.StartNew();
            // Processar roda na thread de arquivos, nunca na janela principal.
            while(!encerrado && espera.ElapsedMilliseconds<esperaMs) {
                lock(trava) { if(!trabalhando || nomes.ContainsKey(termo)) break; }
                Thread.Sleep(15);
            }
            return Consultar(termo,lugar);
        }
        ResultadoPastas Consultar(string termo,string lugar) {
            lock(trava) {
                var resultado=new ResultadoPastas {Completa=pronto && !parcial,EmAndamento=trabalhando};
                List<string> exatos;
                IEnumerable<string> encontrados;
                if(nomes.TryGetValue(termo,out exatos)) { resultado.Exata=true; encontrados=exatos; }
                else {
                    string compacto=Compactar(termo);
                    encontrados=nomes.Where(n=>n.Key.Contains(termo) || compactos[n.Key].Contains(compacto)
                        || Parecido(compacto,compactos[n.Key])).SelectMany(n=>n.Value);
                }
                if(lugar!=null) {
                    string prefixo=lugar.TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar;
                    encontrados=encontrados.Where(p=>String.Equals(p,lugar,StringComparison.OrdinalIgnoreCase)
                        || p.StartsWith(prefixo,StringComparison.OrdinalIgnoreCase));
                }
                var limitados=encontrados.Take(11).ToArray();
                resultado.Mais=limitados.Length>10;
                resultado.Caminhos=limitados.Take(10).OrderBy(p=>p,StringComparer.OrdinalIgnoreCase).ToArray();
                return resultado;
            }
        }
        public ResultadoPastas Aguardar(string termo,string lugar,Action<int> progresso,Func<bool> continuar) {
            termo=Arquivos.Dobrar((termo ?? "").Trim());
            if(lugar!=null) lugar=Arquivos.Canonico(lugar);
            if(termo.Length==0) return new ResultadoPastas();
            Iniciar(); var tempo=Stopwatch.StartNew(); long ultimo=-1000,ultimaConsulta=-1000;
            while(true) {
                if(encerrado || (continuar!=null && !continuar())) throw new OperationCanceledException();
                if(tempo.ElapsedMilliseconds-ultimaConsulta>=250 || !Trabalhando) {
                    var resultado=Consultar(termo,lugar); ultimaConsulta=tempo.ElapsedMilliseconds;
                    if(resultado.Caminhos.Length>0 || !resultado.EmAndamento || tempo.Elapsed>orcamento+TimeSpan.FromSeconds(2)) return resultado;
                }
                if(progresso!=null && tempo.ElapsedMilliseconds-ultimo>=600) { progresso(Consultadas); ultimo=tempo.ElapsedMilliseconds; }
                Thread.Sleep(50);
            }
        }
        static string Compactar(string nome) { return new string(nome.Where(Char.IsLetterOrDigit).ToArray()); }
        static bool Parecido(string a,string b) {
            if(a.Length>80 || b.Length>80) return false;
            int limite=Math.Min(a.Length,b.Length)>=8 ? 2 : 1;
            if(Math.Min(a.Length,b.Length)<5 || Math.Abs(a.Length-b.Length)>limite) return false;
            return AteDuasEdicoes(a,b,0,0,limite);
        }
        static bool AteDuasEdicoes(string a,string b,int i,int j,int restante) {
            while(i<a.Length && j<b.Length && a[i]==b[j]) {i++;j++;}
            if(i==a.Length || j==b.Length) return a.Length-i+b.Length-j<=restante;
            if(restante==0) return false;
            return AteDuasEdicoes(a,b,i+1,j+1,restante-1) || AteDuasEdicoes(a,b,i+1,j,restante-1)
                || AteDuasEdicoes(a,b,i,j+1,restante-1);
        }
        void Construir() {
            var fila=new Queue<string>(); var vistos=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var tempo=Stopwatch.StartNew(); var fatia=Stopwatch.StartNew();
            try {
                foreach(var raiz in raizes() ?? new string[0]) {
                    if(encerrado) return;
                    try { Enfileirar(Arquivos.Canonico(raiz),fila,vistos); }
                    catch(ArgumentException) { } catch(InvalidOperationException) { }
                }
                while(fila.Count>0 && !encerrado) {
                    lock(trava) { if(quantidade>=limite) { parcial=true; break; } }
                    if(tempo.Elapsed>orcamento) { MarcarParcial(); break; }
                    string pasta=fila.Dequeue();
                    lock(trava) consultadas++;
                    try {
                        Arquivos.ConferirAtalhos(pasta);
                        foreach(var filho in listar(pasta)) {
                            if(encerrado) return;
                            if(tempo.Elapsed>orcamento) { MarcarParcial(); break; }
                            Ceder(fatia);
                            string p=Arquivos.Canonico(filho);
                            if(Ignorar(p) || (File.GetAttributes(p)&FileAttributes.ReparsePoint)!=0) continue;
                            if(!Enfileirar(p,fila,vistos)) break;
                            Ceder(fatia);
                        }
                    } catch(UnauthorizedAccessException) { /* Pasta não consultável pelo usuário. */ }
                    catch(IOException) { MarcarParcial(); }
                    catch(InvalidOperationException) { /* Links e caminhos não locais. */ }
                    Ceder(fatia);
                }
            } catch(Exception) { MarcarParcial(); }
            finally { lock(trava) { trabalhando=false; pronto=!encerrado; atualizado=agora(); } }
        }
        void Ceder(Stopwatch fatia) {
            if(fatia.ElapsedMilliseconds>=15) { Thread.Sleep(pausaMs); fatia.Restart(); }
        }
        void MarcarParcial() { lock(trava) parcial=true; }
        bool Enfileirar(string p,Queue<string> fila,HashSet<string> vistos) {
            lock(trava) {
                if(encerrado) return false;
                if(vistos.Contains(p)) return true;
                if(quantidade>=limite) { parcial=true; return false; }
                vistos.Add(p);
                string nome=Arquivos.Dobrar(Path.GetFileName(p));
                List<string> caminhos;
                if(!nomes.TryGetValue(nome,out caminhos)) {
                    nomes[nome]=caminhos=new List<string>(); compactos[nome]=Compactar(nome);
                }
                caminhos.Add(p); quantidade++; fila.Enqueue(p); return true;
            }
        }
        static bool Ignorar(string p) {
            if(Descartar.Contains(Path.GetFileName(p))) return true;
            string windows=Environment.GetFolderPath(Environment.SpecialFolder.Windows);
            return !String.IsNullOrEmpty(windows) && String.Equals(p,windows,StringComparison.OrdinalIgnoreCase);
        }
        static readonly HashSet<string> Descartar=new HashSet<string>(new[] {
            "$Recycle.Bin","System Volume Information","node_modules",".git",".venv","venv","__pycache__",".cache",".nuget"
        },StringComparer.OrdinalIgnoreCase);
        public static IEnumerable<string> RaizesLocais() {
            var resultado=new List<string>();
            // Ancestrais da instalação são candidatos imediatos, sem varrer o disco.
            string app=AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
            for(int i=0;i<10 && !String.IsNullOrEmpty(app);i++) {
                resultado.Add(app); string pai=Path.GetDirectoryName(app); if(pai==app) break; app=pai;
            }
            string perfil=Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            if(!String.IsNullOrEmpty(perfil)) resultado.Add(perfil);
            foreach(var drive in DriveInfo.GetDrives()) {
                try { if(drive.DriveType==DriveType.Fixed && drive.IsReady) resultado.Add(drive.RootDirectory.FullName); }
                catch(IOException) { } catch(UnauthorizedAccessException) { }
            }
            return resultado;
        }
        public void Dispose() { encerrado=true; lock(trava) { nomes.Clear(); compactos.Clear(); quantidade=0; } }
    }
}