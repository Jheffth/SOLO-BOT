using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;

namespace Bella {
    public sealed class ResultadoArquivos {
        public string[] Caminhos=new string[0];
        public bool Completa, Mais, EmAndamento;
    }
    // Somente nomes de arquivos (nunca o conteúdo): um trabalhador em segundo plano, sem rede e sem watchers.
    public sealed class IndiceArquivos : IDisposable {
        readonly object trava=new object();
        readonly Func<IEnumerable<string>> raizes;
        readonly Func<string,IEnumerable<string>> listarPastas, listarArquivos;
        readonly Func<DateTime> agora;
        readonly int limiteArquivos, limitePastas, pausaMs, esperaMs;
        readonly TimeSpan validade, orcamento;
        readonly List<string> caminhos=new List<string>();
        readonly List<string> nomes=new List<string>();
        volatile bool encerrado;
        bool trabalhando, pronto, parcial;
        int consultadas;
        DateTime atualizado;
        public IndiceArquivos(Func<IEnumerable<string>> roots,Func<string,IEnumerable<string>> enumerateDirectories=null,
            Func<string,IEnumerable<string>> enumerateFiles=null,Func<DateTime> clock=null,int maxFiles=500000,int maxDirectories=150000,
            int pauseMilliseconds=30,int waitMilliseconds=1200,TimeSpan? refresh=null,TimeSpan? budget=null) {
            raizes=roots; listarPastas=enumerateDirectories ?? Directory.EnumerateDirectories; listarArquivos=enumerateFiles ?? Directory.EnumerateFiles;
            agora=clock ?? (()=>DateTime.UtcNow); limiteArquivos=Math.Max(1,maxFiles); limitePastas=Math.Max(1,maxDirectories);
            pausaMs=Math.Max(0,pauseMilliseconds); esperaMs=Math.Max(0,waitMilliseconds);
            validade=refresh ?? TimeSpan.FromMinutes(20); orcamento=budget ?? TimeSpan.FromSeconds(180);
        }
        public bool Encerrado { get { return encerrado; } }
        public int Consultadas { get { lock(trava) return consultadas; } }
        public int Quantidade { get { lock(trava) return caminhos.Count; } }
        public bool Trabalhando { get { lock(trava) return trabalhando; } }
        public void Iniciar() {
            lock(trava) {
                if(encerrado || trabalhando || (pronto && agora()-atualizado<validade)) return;
                trabalhando=true; pronto=false; parcial=false; consultadas=0; caminhos.Clear(); nomes.Clear();
                var thread=new Thread(Construir) {IsBackground=true,Name="BellaIndiceArquivos",Priority=ThreadPriority.BelowNormal};
                thread.Start();
            }
        }
        public ResultadoArquivos Aguardar(string termo,string lugar,Action<int> progresso,Func<bool> continuar) {
            termo=Arquivos.Dobrar((termo ?? "").Trim());
            if(lugar!=null) lugar=Arquivos.Canonico(lugar);
            if(termo.Length==0) return new ResultadoArquivos();
            Iniciar(); var tempo=Stopwatch.StartNew(); long ultimo=-1000,ultimaConsulta=-1000;
            while(true) {
                if(encerrado || (continuar!=null && !continuar())) throw new OperationCanceledException();
                if(tempo.ElapsedMilliseconds-ultimaConsulta>=250 || !Trabalhando) {
                    var resultado=Consultar(termo,lugar,tempo.ElapsedMilliseconds>=esperaMs || !Trabalhando); ultimaConsulta=tempo.ElapsedMilliseconds;
                    // Acertos exatos aparecem na hora; achados aproximados esperam o fim da varredura.
                    if(resultado.Caminhos.Length>0 || !resultado.EmAndamento || tempo.Elapsed>orcamento+TimeSpan.FromSeconds(2)) return resultado;
                }
                if(progresso!=null && tempo.ElapsedMilliseconds-ultimo>=600) { progresso(Consultadas); ultimo=tempo.ElapsedMilliseconds; }
                Thread.Sleep(50);
            }
        }
        public ResultadoArquivos Buscar(string termo,string lugar=null) {
            termo=Arquivos.Dobrar((termo ?? "").Trim());
            if(lugar!=null) lugar=Arquivos.Canonico(lugar);
            if(termo.Length==0 || encerrado) return new ResultadoArquivos();
            Iniciar(); var espera=Stopwatch.StartNew();
            while(!encerrado && espera.ElapsedMilliseconds<esperaMs) { if(!Trabalhando) break; Thread.Sleep(15); }
            return Consultar(termo,lugar,true);
        }
        static string[] Palavras(string termo) {
            return termo.Split(new[] {' ','_','-','.',',','(',')','[',']'},StringSplitOptions.RemoveEmptyEntries);
        }
        static string Compactar(string nome) { return new string(nome.Where(Char.IsLetterOrDigit).ToArray()); }
        ResultadoArquivos Consultar(string termo,string lugar,bool aproximar) {
            string[] palavras=Palavras(termo); if(palavras.Length==0) palavras=new[] {termo};
            string prefixo=lugar==null ? null : lugar.TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar;
            var pontuados=new List<KeyValuePair<int,string>>();
            bool completa, andamento;
            lock(trava) {
                completa=pronto && !parcial; andamento=trabalhando;
                for(int i=0;i<nomes.Count;i++) {
                    string n=nomes[i]; int pontos=0;
                    if(n.IndexOf(termo,StringComparison.Ordinal)>=0) {
                        string semExt=Path.GetFileNameWithoutExtension(n);
                        pontos=n==termo ? 100 : semExt==termo ? 90 : n.StartsWith(termo,StringComparison.Ordinal) ? 80 : 60;
                    } else if(palavras.All(p=>n.IndexOf(p,StringComparison.Ordinal)>=0)) pontos=50;
                    if(pontos==0) continue;
                    if(prefixo!=null && !caminhos[i].StartsWith(prefixo,StringComparison.OrdinalIgnoreCase)) continue;
                    pontuados.Add(new KeyValuePair<int,string>(pontos,caminhos[i]));
                }
                if(pontuados.Count==0 && aproximar) {
                    string compacto=Compactar(System.Text.RegularExpressions.Regex.Replace(termo,@"\.[a-z0-9]{1,8}$",""));
                    if(compacto.Length>=5) for(int i=0;i<nomes.Count;i++) {
                        string c=Compactar(Path.GetFileNameWithoutExtension(nomes[i]));
                        if(c.Length<5 || Math.Abs(c.Length-compacto.Length)>2 || !Parecido(compacto,c)) continue;
                        if(prefixo!=null && !caminhos[i].StartsWith(prefixo,StringComparison.OrdinalIgnoreCase)) continue;
                        pontuados.Add(new KeyValuePair<int,string>(30,caminhos[i]));
                        if(pontuados.Count>=200) break;
                    }
                }
            }
            // Mesma pontuação: o arquivo mexido por último vem primeiro (só consulta o disco dos melhores).
            var melhores=pontuados.OrderByDescending(p=>p.Key).ThenBy(p=>p.Value.Length).Take(60).ToList();
            var ordenados=melhores.GroupBy(p=>p.Key).OrderByDescending(g=>g.Key)
                .SelectMany(g=>g.OrderByDescending(p=>Modificado(p.Value)).ThenBy(p=>p.Value,StringComparer.OrdinalIgnoreCase)).Select(p=>p.Value).ToArray();
            return new ResultadoArquivos {Completa=completa,EmAndamento=andamento,Mais=pontuados.Count>10,Caminhos=ordenados.Take(10).ToArray()};
        }
        static DateTime Modificado(string p) {
            try { return File.GetLastWriteTimeUtc(p); } catch(Exception) { return DateTime.MinValue; }
        }
        static bool Parecido(string a,string b) {
            int limite=Math.Min(a.Length,b.Length)>=8 ? 2 : 1;
            return AteEdicoes(a,b,0,0,limite);
        }
        static bool AteEdicoes(string a,string b,int i,int j,int restante) {
            while(i<a.Length && j<b.Length && a[i]==b[j]) {i++;j++;}
            if(i==a.Length || j==b.Length) return a.Length-i+b.Length-j<=restante;
            if(restante==0) return false;
            return AteEdicoes(a,b,i+1,j+1,restante-1) || AteEdicoes(a,b,i+1,j,restante-1) || AteEdicoes(a,b,i,j+1,restante-1);
        }
        void Construir() {
            var fila=new Queue<string>(); var vistos=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var tempo=Stopwatch.StartNew(); var fatia=Stopwatch.StartNew(); var lote=new List<string>();
            try {
                foreach(var raiz in raizes() ?? new string[0]) {
                    if(encerrado) return;
                    try { string c=Arquivos.Canonico(raiz); if(vistos.Add(c)) fila.Enqueue(c); }
                    catch(ArgumentException) { } catch(InvalidOperationException) { }
                }
                while(fila.Count>0 && !encerrado) {
                    if(vistos.Count>limitePastas) { MarcarParcial(); break; }
                    if(tempo.Elapsed>orcamento) { MarcarParcial(); break; }
                    string pasta=fila.Dequeue();
                    lock(trava) consultadas++;
                    try {
                        Arquivos.ConferirAtalhos(pasta);
                        lote.Clear();
                        foreach(var arquivo in listarArquivos(pasta)) {
                            if(encerrado) return;
                            lote.Add(arquivo);
                        }
                        if(!Registrar(lote)) { MarcarParcial(); break; }
                        Ceder(fatia);
                        foreach(var filho in listarPastas(pasta)) {
                            if(encerrado) return;
                            if(tempo.Elapsed>orcamento) { MarcarParcial(); break; }
                            Ceder(fatia);
                            string p=Arquivos.Canonico(filho);
                            if(Ignorar(p) || vistos.Contains(p) || (File.GetAttributes(p)&FileAttributes.ReparsePoint)!=0) continue;
                            vistos.Add(p); fila.Enqueue(p);
                        }
                    } catch(UnauthorizedAccessException) { /* Pasta não consultável pelo usuário. */ }
                    catch(IOException) { MarcarParcial(); }
                    catch(InvalidOperationException) { /* Links e caminhos não locais. */ }
                    Ceder(fatia);
                }
                if(fila.Count>0 && !encerrado) MarcarParcial();
            } catch(Exception) { MarcarParcial(); }
            finally { lock(trava) { trabalhando=false; pronto=!encerrado; atualizado=agora(); } }
        }
        bool Registrar(List<string> lote) {
            lock(trava) {
                if(encerrado) return false;
                foreach(var p in lote) {
                    if(caminhos.Count>=limiteArquivos) return false;
                    string nome=Path.GetFileName(p);
                    if(String.IsNullOrEmpty(nome) || Ruido.Contains(Path.GetExtension(nome))) continue;
                    caminhos.Add(p); nomes.Add(Arquivos.Dobrar(nome));
                }
                return true;
            }
        }
        void Ceder(Stopwatch fatia) {
            if(fatia.ElapsedMilliseconds>=15) { Thread.Sleep(pausaMs); fatia.Restart(); }
        }
        void MarcarParcial() { lock(trava) parcial=true; }
        static bool Ignorar(string p) {
            if(Descartar.Contains(Path.GetFileName(p))) return true;
            string windows=Environment.GetFolderPath(Environment.SpecialFolder.Windows);
            return !String.IsNullOrEmpty(windows) && String.Equals(p,windows,StringComparison.OrdinalIgnoreCase);
        }
        // Pastas de sistema/aplicativos e caches: ruído para quem procura os próprios arquivos.
        static readonly HashSet<string> Descartar=new HashSet<string>(new[] {
            "$Recycle.Bin","System Volume Information","node_modules",".git",".venv","venv","__pycache__",".cache",".nuget",
            "AppData","Program Files","Program Files (x86)","ProgramData","Recovery","$WINDOWS.~BT","$WinREAgent",".gradle",".m2",".npm",
            "site-packages","WindowsApps","Windows.old"
        },StringComparer.OrdinalIgnoreCase);
        static readonly HashSet<string> Ruido=new HashSet<string>(new[] {".tmp",".dll",".sys",".lnk",".ini",".dat",".log",".pyc",".obj",".pdb",".cache"},StringComparer.OrdinalIgnoreCase);
        // Perfil do usuário primeiro (onde ficam os documentos), depois a instalação e os discos fixos.
        public static IEnumerable<string> RaizesLocais() {
            var resultado=new List<string>();
            string perfil=Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            if(!String.IsNullOrEmpty(perfil)) resultado.Add(perfil);
            foreach(var r in IndicePastas.RaizesLocais()) if(!resultado.Contains(r,StringComparer.OrdinalIgnoreCase)) resultado.Add(r);
            return resultado;
        }
        public void Dispose() { encerrado=true; lock(trava) { caminhos.Clear(); nomes.Clear(); } }
    }
}
