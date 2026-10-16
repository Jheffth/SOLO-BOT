using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace Bella {
    public sealed class AcaoPrograma {
        public string comando_id {get;set;}
        public string acao {get;set;}
        public string texto {get;set;}
        public string motivo {get;set;}
    }
    public sealed class Programas {
        readonly Func<ComandoPasta[]> comandos;
        readonly IEditorWord word;
        readonly Action<string> abrir;
        public Programas(Func<ComandoPasta[]> catalogo,IEditorWord editor=null,Action<string> open=null) {
            comandos=catalogo; word=editor ?? new EditorWord(); abrir=open ?? Abrir;
        }
        public static bool Tipo(string tipo) { return tipo=="word" || tipo=="programa"; }
        ComandoPasta[] Catalogo {get {return (comandos() ?? new ComandoPasta[0]).Where(c=>Tipo(c.Tipo)).ToArray();}}
        public static string Executavel(string caminho) {
            if(String.IsNullOrWhiteSpace(caminho) || !Path.IsPathRooted(caminho) || caminho.StartsWith(@"\\") || caminho.IndexOf('"')>=0)
                throw new InvalidOperationException("Selecione um programa .exe instalado neste computador, sem argumentos.");
            string p=Arquivos.Canonico(caminho);
            if(!String.Equals(Path.GetExtension(p),".exe",StringComparison.OrdinalIgnoreCase) || !File.Exists(p))
                throw new InvalidOperationException("Selecione um arquivo .exe existente, sem atalhos ou scripts.");
            Arquivos.ConferirAtalhos(p); return p;
        }
        [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hWnd);
        [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr hWnd,int nCmdShow);
        static void Abrir(string caminho) {
            caminho=Executavel(caminho);
            foreach(var processo in Process.GetProcessesByName(Path.GetFileNameWithoutExtension(caminho))) {
                using(processo) {
                    try {
                        if(String.Equals(processo.MainModule.FileName,caminho,StringComparison.OrdinalIgnoreCase) && processo.MainWindowHandle!=IntPtr.Zero) {
                            ShowWindow(processo.MainWindowHandle,9); SetForegroundWindow(processo.MainWindowHandle); return;
                        }
                    } catch(System.ComponentModel.Win32Exception) { }
                }
            }
            using(var processo=Process.Start(new ProcessStartInfo {FileName=caminho,UseShellExecute=false,Arguments="",WorkingDirectory=Path.GetDirectoryName(caminho)})) { }
        }
        public static bool Casar(ComandoPasta c,string texto,out string pedido) {
            pedido=null;
            if(!c.Frase.Contains("{pedido}")) return ComandosPastas.Chave(c.Frase)==ComandosPastas.Chave(texto);
            var partes=c.Frase.Split(new[] {"{pedido}"},StringSplitOptions.None);
            if(partes.Length!=2) return false;
            string padrao="^"+Regex.Escape(partes[0].Trim())+@"\s+(?<pedido>.+?)"+
                (partes[1].Trim().Length==0 ? "" : @"\s+"+Regex.Escape(partes[1].Trim()))+"$";
            var m=Regex.Match((texto ?? "").Trim(),padrao,RegexOptions.IgnoreCase|RegexOptions.Singleline);
            if(!m.Success) m=Regex.Match(ComandosPastas.Pedido(texto),padrao,RegexOptions.IgnoreCase|RegexOptions.Singleline);
            if(!m.Success) return false;
            pedido=m.Groups["pedido"].Value; return true;
        }
        bool Provavel(string texto,ComandoPasta[] catalogo) {
            string t=Arquivos.Dobrar(ComandosPastas.Pedido(texto));
            if(t.StartsWith("/") || Regex.IsMatch(t,@"^(nao|nunca|cancele|cancelar)\b")) return false;
            if(!Regex.IsMatch(t,@"\bword\b") && Regex.IsMatch(t,@"\b(rotina|missao|meta|saldo|banco|conta|recebi|gastei)\b")) return false;
            return catalogo.Any(c=>c.Tipo=="word") && Regex.IsMatch(t,@"^(escreva|escrever|digite|ditar|faca|crie|redija|gere|elabore)\b")
                || Regex.IsMatch(t,@"\bword\b") && catalogo.Any(c=>c.Tipo=="word")
                || Regex.IsMatch(t,@"^(abrir|abra|abre|acesse|inicie)\b") && catalogo.Any(c=>ComandosPastas.Chave(c.Frase).Split(' ').Any(p=>p.Length>3 && !Regex.IsMatch(p,@"^(abrir|minha|meus|programa)$") && Regex.IsMatch(t,@"\b"+Regex.Escape(p)+@"\b")));
        }
        static Reply Resposta(string texto,string falar=null) {return new Reply {texto="**🖥️ Aplicativos**\n"+texto,falar=falar ?? texto};}
        public async Task<Reply> Atender(string texto,Func<string,ComandoPasta[],Task<AcaoPrograma>> interpretar,Func<bool> continuar=null,Dictionary<string,long> tempos=null) {
            var catalogo=Catalogo; if(catalogo.Length==0) return null;
            var matches=new List<Tuple<ComandoPasta,string>>();
            var teste=Regex.Match(texto ?? "",@"^/arquivos comando ([a-f0-9]{32})$");
            foreach(var c in catalogo) {string pedido; if(Casar(c,texto,out pedido) || teste.Success && teste.Groups[1].Value==c.Id) matches.Add(Tuple.Create(c,pedido));}
            if(matches.Count>1) return Resposta("Mais de um comando de aplicativo corresponde. Use uma frase mais específica.");
            if(matches.Count==0 && !Provavel(texto,catalogo)) return null;
            AcaoPrograma acao=null;
            // O tipo Word é automático: ditado e abertura reconhecíveis não precisam de rede.
            if(matches.Count==0) {
                var wordPadrao=catalogo.FirstOrDefault(c=>c.Tipo=="word");
                var literal=Regex.Match((texto ?? "").Trim(),@"^(?:escreva|digite|ditar|escrever)\s+(?<texto>.+)$",RegexOptions.IgnoreCase|RegexOptions.Singleline);
                if(wordPadrao!=null && literal.Success && !Regex.IsMatch(Arquivos.Dobrar(literal.Groups["texto"].Value),@"^(?:no|na|em|pelo|pela)\s+(?:word|excel|notepad|bloco|navegador)\b"))
                    acao=new AcaoPrograma {comando_id=wordPadrao.Id,acao="escrever",texto=literal.Groups["texto"].Value};
                if(wordPadrao!=null && Regex.IsMatch(ComandosPastas.Chave(texto),@"^abrir (?:microsoft )?word$"))
                    acao=new AcaoPrograma {comando_id=wordPadrao.Id,acao="abrir",texto=""};
            }
            if(matches.Count==1) {
                var c=matches[0].Item1; string conteudo=matches[0].Item2;
                if(c.Frase.Contains("{pedido}") && String.IsNullOrWhiteSpace(conteudo)) return Resposta("Diga o comando com o texto ou pedido no lugar de {pedido}.");
                if(c.Tipo=="programa" || conteudo==null && !Regex.IsMatch(Arquivos.Dobrar(texto),@"^(escreva|escrever|digite|ditar|faca|crie|redija|gere|elabore)\b")) acao=new AcaoPrograma {comando_id=c.Id,acao="abrir",texto=""};
                else if(Regex.IsMatch(Arquivos.Dobrar(c.Frase),@"^(escreva|escrever|digite|ditar|anote)\s+\{pedido\}$"))
                    acao=new AcaoPrograma {comando_id=c.Id,acao="escrever",texto=conteudo};
            }
            if(acao==null) {
                var relogio=Stopwatch.StartNew();
                try {acao=await interpretar(texto,matches.Count==1 ? new[] {matches[0].Item1} : catalogo);}
                catch(UnauthorizedAccessException) {throw;}
                catch(Exception) {return Resposta("A interpretação está indisponível. Tente um comando direto cadastrado, como Escreva seguido do texto.");}
                finally {if(tempos!=null) tempos["IA do aplicativo"]=relogio.ElapsedMilliseconds;}
            }
            if(continuar!=null && !continuar()) throw new OperationCanceledException();
            if(acao!=null && acao.motivo=="indisponivel") return Resposta("A IA está indisponível no momento. Ditados diretos, como Escreva seguido do texto, e abertura de programas continuam disponíveis.");
            var permitidos=matches.Count==1 ? new[] {matches[0].Item1} : catalogo;
            var escolhido=acao==null ? null : permitidos.SingleOrDefault(c=>c.Id==acao.comando_id);
            if(escolhido==null || acao.acao!="abrir" && acao.acao!="escrever" || escolhido.Tipo!="word" && acao.acao!="abrir")
                return Resposta("Não identifiquei uma ação segura para o aplicativo. Informe o programa e o que deseja escrever.");
            if(acao.acao=="escrever" && (String.IsNullOrWhiteSpace(acao.texto) || acao.texto.Length>12000 || acao.texto.IndexOf('\0')>=0))
                return Resposta("Não recebi um texto válido para inserir. Tente um pedido mais curto.");
            if(acao.acao=="abrir" && !String.IsNullOrEmpty(acao.texto)) return Resposta("O pedido de abertura trouxe dados inesperados. Faça o comando novamente.");
            var fim=new TaskCompletionSource<Reply>();
            long duracao=0;
            var thread=new Thread(()=> {
                var relogio=Stopwatch.StartNew();
                Reply resposta=null; bool cancelado=false;
                try {
                    if(continuar!=null && !continuar()) throw new OperationCanceledException();
                    string resultado;
                    if(escolhido.Tipo=="word") resultado=word.Executar(acao.acao=="escrever" ? acao.texto : null);
                    else {abrir(Executavel(escolhido.Caminho)); resultado="Programa aberto ou trazido para a frente.";}
                    resposta=Resposta(resultado,acao.acao=="escrever" ? "Escrevi no Word." : "O programa está pronto.");
                } catch(OperationCanceledException) {cancelado=true;}
                catch(Exception erro) {resposta=Resposta(erro.Message,"Não consegui concluir. Confira a mensagem na tela.");}
                finally {duracao=relogio.ElapsedMilliseconds;}
                if(cancelado) fim.SetCanceled(); else fim.SetResult(resposta);
            });
            thread.IsBackground=true; thread.SetApartmentState(ApartmentState.STA); thread.Start();
            var conclusao=await fim.Task;
            if(tempos!=null) tempos["Aplicativo"]=duracao;
            return conclusao;
        }
    }
}
