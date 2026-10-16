using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

namespace Bella {
    internal static class ProgramasTestes {
        sealed class WordFalso : IEditorWord {
            public int Chamadas; public string Texto;
            public string Executar(string texto) { Check(Thread.CurrentThread.GetApartmentState()==ApartmentState.STA,"Word executa em STA"); Chamadas++; Texto=texto; return "Documento de teste pronto"; }
        }
        static void Check(bool ok,string texto) {if(!ok) throw new Exception("Aplicativos: "+texto);}
        public static void Run() {
            var editar=new ComandoPasta {Tipo="word",Frase="Escreva {pedido}"};
            var gerar=new ComandoPasta {Tipo="word",Frase="Faça {pedido}"};
            var abrir=new ComandoPasta {Tipo="word",Frase="Abrir Word"};
            var editor=new WordFalso();
            var programas=new Programas(()=>new[] {editar,gerar,abrir},editor);
            int ia=0;
            Func<string,ComandoPasta[],Task<AcaoPrograma>> interpretar=(texto,comandos)=> {
                ia++; return Task.FromResult(new AcaoPrograma {comando_id=comandos[0].Id,acao="escrever",texto="O amor é uma flor.\nFloresce com calor."});
            };
            var tempos=new Dictionary<string,long>();
            var r=programas.Atender("Escreva O amor é lindo, por favor.",interpretar,tempos:tempos).GetAwaiter().GetResult();
            Check(editor.Texto=="O amor é lindo, por favor." && ia==0 && editor.Chamadas==1,"ditado literal preserva acentos, caixa e pontuação sem pedir IA");
            Check(tempos.ContainsKey("Aplicativo") && !tempos.ContainsKey("IA do aplicativo"),"tempos distinguem ação local de IA");
            programas.Atender("Faça uma rima com amor",interpretar).GetAwaiter().GetResult();
            Check(ia==1 && editor.Chamadas==2 && editor.Texto.Contains("flor"),"geração requer uma só interpretação e insere o resultado");
            programas.Atender("Abra o Word",interpretar).GetAwaiter().GetResult();
            Check(editor.Chamadas==3 && editor.Texto==null && ia==1,"abertura direta não gasta IA");
            foreach(var pedido in new[] {"/fin saldo","crie uma rotina diária de treino","não escreva amor"})
                Check(programas.Atender(pedido,interpretar).GetAwaiter().GetResult()==null,"comandos alheios e negações não escrevem no Word");
            int antes=editor.Chamadas;
            programas.Atender("Faça uma rima",(t,c)=>Task.FromResult(new AcaoPrograma {comando_id=abrir.Id,acao="escrever",texto="errado"})).GetAwaiter().GetResult();
            Check(editor.Chamadas==antes,"resposta de IA não pode trocar o comando selecionado");
            programas.Atender("Faça uma rima",(t,c)=>Task.FromResult(new AcaoPrograma {comando_id=gerar.Id,acao="salvar",texto="errado"})).GetAwaiter().GetResult();
            Check(editor.Chamadas==antes,"ação fora da lista não executa");
            bool cancelou=false;
            try {programas.Atender("Faça uma rima",interpretar,()=>false).GetAwaiter().GetResult();} catch(OperationCanceledException) {cancelou=true;}
            Check(cancelou && editor.Chamadas==antes,"cancelamento após IA impede execução");
            var arquivos=new Arquivos(()=>new string[0],commands:()=>new[] {editar,abrir});
            Check(Array.TrueForAll(arquivos.CatalogoComandos,c=>!Programas.Tipo(c.Tipo)),"programas não entram no motor de arquivos");
            var cadastrados=ComandosPastas.Atualizar(new ComandoPasta[0],null,"Escreva {pedido}","",tipo:"word");
            Check(cadastrados[0].Tipo=="word" && cadastrados[0].Caminho=="","Word configura sem caminho de executável");
            foreach(var caminho in new[] {@"C:\Windows\System32\cmd.exe /c whoami",@"C:\teste.ps1",@"\\servidor\teste.exe"}) {
                bool recusou=false; try {Programas.Executavel(caminho);} catch {recusou=true;}
                Check(recusou,"recusa argumentos, scripts e executáveis de rede");
            }
            string conteudo;
            Check(Programas.Casar(editar,"Escreva primeira linha\nsegunda linha",out conteudo) && conteudo=="primeira linha\nsegunda linha","ditado aceita parágrafos");
            var simples=new Programas(()=>new[] {abrir},editor);
            int iaAntes=ia;
            simples.Atender("Escreva o amor é lindo",interpretar).GetAwaiter().GetResult();
            Check(editor.Texto=="o amor é lindo" && ia==iaAntes,"um cadastro Word já permite ditado claro sem gastar IA");
            string executavel=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"Bella.exe"), aberto=null;
            var outro=new ComandoPasta {Tipo="programa",Frase="Abrir programa de teste",Caminho=executavel};
            var lancador=new Programas(()=>new[] {outro},editor,p=>aberto=p);
            lancador.Atender(outro.Frase,interpretar).GetAwaiter().GetResult();
            Check(aberto==executavel && ia==iaAntes,"programa configurado abre por caminho validado sem IA nem argumentos");
        }
        public static void WordReal() {
            var processos=Process.GetProcessesByName("WINWORD"); bool aberto=processos.Length>0;
            foreach(var processo in processos) processo.Dispose();
            if(aberto) throw new InvalidOperationException("Feche seus documentos do Word antes do teste isolado; nenhum documento existente foi alterado.");
            object aplicativo=null, documento=null, faixa=null;
            try {
                aplicativo=Activator.CreateInstance(Type.GetTypeFromProgID("Word.Application"));
                dynamic app=aplicativo; app.Visible=true;
                documento=app.Documents.Add(); dynamic doc=documento;
                doc.Content.Text="Texto original.";
                faixa=doc.Range(0,5); ((dynamic)faixa).Select();
                var editor=new EditorWord(); editor.Executar(" NOVO");
                Check(((string)doc.Content.Text).StartsWith("Texto NOVO original."),"Word real preserva o texto selecionado e insere após a seleção");
                editor.Executar(null);
                Check(app.Documents.Count==1,"Word real é reutilizado sem criar documento duplicado");
                Check(!doc.Saved,"Word permanece sem salvamento automático");
            } finally {
                if(documento!=null) {try {((dynamic)documento).Close(0);} finally {Marshal.ReleaseComObject(documento);}}
                if(faixa!=null) Marshal.ReleaseComObject(faixa);
                if(aplicativo!=null) {try {if(((dynamic)aplicativo).Documents.Count==0) ((dynamic)aplicativo).Quit(0);} finally {Marshal.ReleaseComObject(aplicativo);}}
            }
        }
    }
}
