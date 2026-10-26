using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;

namespace Bella {
    // Busca de arquivos pelo nome em todo o computador, sem cadastro e sem exigir pasta liberada.
    internal static class ArquivosLivresTestes {
        static void Check(bool ok,string message) { if(!ok) throw new Exception("Arquivos livres: "+message); }
        static void Pronto(IndiceArquivos indice) {
            indice.Iniciar(); var tempo=Stopwatch.StartNew();
            while(indice.Trabalhando && tempo.ElapsedMilliseconds<5000) Thread.Sleep(5);
            Check(!indice.Trabalhando,"índice sintético conclui em cinco segundos");
        }
        static void Escrever(string caminho) {
            Directory.CreateDirectory(Path.GetDirectoryName(caminho)); File.WriteAllText(caminho,"fixture inerte");
        }
        public static void Run(string baseDirectory) {
            string raiz=Path.Combine(baseDirectory,"self-test-arquivos-livres-"+Guid.NewGuid().ToString("N"));
            string docs=Path.Combine(raiz,"docs"), contrato=Path.Combine(docs,"sub","contrato_aluguel.docx");
            string relatorio1=Path.Combine(docs,"Relatório Final 2026.pdf"), relatorio2=Path.Combine(raiz,"outro","relatorio final.pdf");
            string plano=Path.Combine(raiz,"unico","Plano de Voo.txt"), programa=Path.Combine(raiz,"x","programa.exe");
            string ignorado=Path.Combine(raiz,"node_modules","ignorado.pdf");
            foreach(var p in new[] {contrato,relatorio1,relatorio2,plano,programa,ignorado}) Escrever(p);
            try {
                var abertos=new List<string>();
                using(var indice=new IndiceArquivos(()=>new[] {raiz},pauseMilliseconds:0)) {
                    var files=new Arquivos(()=>new string[0],p=>abertos.Add(p),fileIndex:indice);
                    Pronto(indice);
                    Check(indice.Quantidade==5,"indexa cinco arquivos e ignora node_modules ("+indice.Quantidade+")");

                    var r=files.Processar("buscar arquivo relatorio final").GetAwaiter().GetResult();
                    Check(r.CodigoVoz=="escolha" && r.opcoes!=null && r.opcoes.Length==2,"nome sem acento acha os dois relatórios");
                    Check(r.opcoes.Any(o=>o.rotulo==relatorio1) && r.opcoes.Any(o=>o.rotulo==relatorio2),"mostra os caminhos completos");
                    Check(!r.texto.Contains("ignorado") && r.SomenteLocal,"resultado fica local e não lista pasta ignorada");
                    files.Processar("1").GetAwaiter().GetResult();
                    Check(abertos.Count==1 && (abertos[0]==relatorio1 || abertos[0]==relatorio2),"número abre o arquivo escolhido");

                    abertos.Clear();
                    r=files.Processar("abrir arquivo contrato aluguel.docx").GetAwaiter().GetResult();
                    Check(r.CodigoVoz=="aberto" && abertos.SequenceEqual(new[] {contrato}),"resultado único abre direto");

                    r=files.Processar("onde está o arquivo Plano de Voo.txt").GetAwaiter().GetResult();
                    Check(r.texto.Contains(plano) || (r.opcoes!=null && r.opcoes.Any(o=>o.rotulo==plano)),"pergunta de caminho devolve o caminho completo");

                    abertos.Clear();
                    r=files.Processar("abrir arquivo programa.exe").GetAwaiter().GetResult();
                    Check(abertos.Count==1 && abertos[0]==Path.GetDirectoryName(programa),"executável nunca é executado: abre só a pasta");

                    r=files.Processar("buscar arquivo ignorado").GetAwaiter().GetResult();
                    Check(r.CodigoVoz=="vazio","pasta ignorada não aparece");

                    abertos.Clear();
                    r=files.Processar("abrir arquivo contrato aluguell.docx").GetAwaiter().GetResult();
                    Check(abertos.SequenceEqual(new[] {contrato}),"pequeno erro de digitação ainda acha o arquivo");

                    r=files.Processar("buscar arquivo relatorio final em "+docs).GetAwaiter().GetResult();
                    Check(r.CodigoVoz=="escolha" || r.CodigoVoz=="aberto","escopo por caminho completo funciona");
                    Check(r.opcoes==null || r.opcoes.All(o=>o.rotulo.StartsWith(docs)),"escopo limita à pasta pedida");

                    Check(files.PedidoLocal("procure o arquivo contrato"),"pedido de arquivo é tratado localmente");
                    Check(!files.PedidoLocal("abrir minha missão"),"assuntos do app não viram busca de arquivo");
                }
            } finally {
                try { Directory.Delete(raiz,true); } catch(IOException) { } catch(UnauthorizedAccessException) { }
            }
        }
    }
}
