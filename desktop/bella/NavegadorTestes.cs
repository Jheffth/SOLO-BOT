using System;
using System.Collections.Generic;
using System.Linq;
using System.Web.Script.Serialization;

namespace Bella {
    internal static class NavegadorTestes {
        static void Check(bool ok,string texto) { if(!ok) throw new Exception("Navegador: "+texto); }
        static void Recusa(Action acao,string texto) {
            bool recusou=false; try {acao();} catch(InvalidOperationException) {recusou=true;}
            Check(recusou,texto);
        }
        public static void Run() {
            var abertos=new List<string>(); ComandoPasta[] comandos=new ComandoPasta[0];
            DateTime tempo=new DateTime(2026,10,13,20,0,0,DateTimeKind.Utc);
            var local=new Arquivos(()=>new string[0],p=>abertos.Add(p),clock:()=>tempo,commands:()=>comandos);
            foreach(string frase in new[] {"Pesquisar sobre Escrita criativa", "Quero que pesquise sobre Escrita criativa.", "Pesquise Escrita criativa no Google."}) {
                var r=local.Processar(frase).GetAwaiter().GetResult();
                Check(r.CodigoVoz=="pesquisa_aberta" && abertos.Last()=="https://www.google.com/search?q=Escrita%20criativa","pesquisa livre abre resultados no Google: "+frase);
            }
            var reply=local.Atender("Pesquisar no YouTube sobre técnicas de escrita");
            Check(reply.CodigoVoz=="pesquisa_aberta" && new Uri(abertos.Last()).Host=="www.youtube.com","YouTube usa seu destino de busca");
            reply=local.Atender("Pesquisar no Maps sobre cafeterias em São Paulo");
            Check(reply.CodigoVoz=="pesquisa_aberta" && abertos.Last().Contains("api=1&query=cafeterias%20em%20S%C3%A3o%20Paulo"),"Maps preserva local e acentos");
            reply=local.Atender("Pesquisar quem fundou YouTube");
            Check(new Uri(abertos.Last()).Host=="www.google.com","nome de site dentro do assunto nao troca motor");
            reply=local.Atender("Pesquisar sobre C# & a=1 + 50% \"teste\"");
            Check(Uri.UnescapeDataString(new Uri(abertos.Last()).Query.Substring(3))=="C# & a=1 + 50% \"teste\"","assunto escapa pontuacao sem injetar parametros");
            int antes=abertos.Count;
            Check(local.Atender("Não pesquise sobre escrita criativa").CodigoVoz=="cancelado" && abertos.Count==antes,"negacao nao abre navegador");
            Check(local.Atender("buscar arquivo rascunho.txt").CodigoVoz=="vazio" && abertos.Count==antes,"busca de arquivo nao vira pesquisa na internet");
            Check(local.Atender("pesquisar arquivo rascunho.txt").CodigoVoz=="vazio" && abertos.Count==antes,"pesquisar arquivo explicito continua local");
            Check(local.Atender("pesquisar sobre pastas no Windows").CodigoVoz=="pesquisa_aberta","assunto de internet pode mencionar pastas");
            Check(local.Atender("saldo")==null,"comando financeiro continua no hub");
            Check(local.Atender("Pesquisar no Google sobre").CodigoVoz=="pedir_assunto","pesquisa sem tema pergunta antes de abrir");
            Check(local.Atender("Escrita criativa").CodigoVoz=="pesquisa_aberta","resposta de assunto continua pesquisa local");
            Check(local.Atender("Pesquisar no Google sobre").CodigoVoz=="pedir_assunto","nova pesquisa pede assunto");
            tempo=tempo.AddMinutes(6);
            Check(local.Atender("Escrita criativa").CodigoVoz=="expirou","assunto pendente expira");
            local.Atender("Pesquisar no Google sobre");
            Check(local.Atender("cancelar").CodigoVoz=="cancelado","cancela assunto pendente");
            comandos=ComandosPastas.Atualizar(comandos,null,"Abrir minha agenda","https://calendar.google.com/",tipo:"site");
            Check(local.Processar("Quero que abra a minha agenda").GetAwaiter().GetResult().CodigoVoz=="site_aberto" && abertos.Last()=="https://calendar.google.com/","site cadastrado usa navegador com frase natural");
            Recusa(()=>ComandosPastas.Atualizar(comandos,null,"Executar JavaScript","javascript:alert(1)",tipo:"site"),"site nao executa JavaScript");
            Recusa(()=>ComandosPastas.Atualizar(comandos,null,"Arquivo local","file:///C:/Windows",tipo:"site"),"site nao abre esquema de arquivo");
            Recusa(()=>ComandosPastas.Atualizar(comandos,null,"Comando local","cmd:comando",tipo:"site"),"protocolo executavel recusado");
            Recusa(()=>ComandosPastas.Atualizar(comandos,null,"Site com senha","https://user:senha@example.org",tipo:"site"),"URL com credenciais recusada");
            Recusa(()=>ComandosPastas.Atualizar(comandos,null,"Script","",tipo:"powershell"),"tipo arbitrario nao salvo");
            comandos=ComandosPastas.Atualizar(comandos,null,"Hora de estudar escrita","",tipo:"google",termo:"Escrita criativa");
            Check(local.Atender("Hora de estudar escrita").CodigoVoz=="pesquisa_aberta" && abertos.Last().EndsWith("q=Escrita%20criativa"),"busca de assunto fixo");
            string id=comandos.Last().Id;
            comandos=ComandosPastas.Atualizar(comandos,id,"Hora de estudar escrita","",tipo:"youtube",termo:"Escrita criativa");
            Check(local.Atender("Hora de estudar escrita").CodigoVoz=="pesquisa_aberta" && new Uri(abertos.Last()).Host=="www.youtube.com","editar muda tipo sem mudar identidade");
            comandos=ComandosPastas.Atualizar(comandos,null,"Investigar {assunto}","",tipo:"google");
            Check(local.Atender("Investigar ideias para ficção científica").CodigoVoz=="pesquisa_aberta" && abertos.Last().Contains("fic%C3%A7%C3%A3o"),"frase variavel conserva assunto e acentos");
            reply=local.Atender("/arquivos comando "+comandos.Last().Id);
            Check(reply.CodigoVoz=="pedir_assunto" && local.TemEscolha,"Testar frase variavel pergunta assunto");
            Check(local.Atender("personagens").CodigoVoz=="pesquisa_aberta","tema do teste abre resultado");
            Recusa(()=>ComandosPastas.Atualizar(comandos,null,"Site {assunto}","https://example.org",tipo:"site"),"variavel nao gera enderecos de sites");
            Recusa(()=>ComandosPastas.Atualizar(comandos,null,"Pesquisar {assunto} {assunto}","",tipo:"google"),"variavel duplicada recusada");
            Recusa(()=>ComandosPastas.Atualizar(comandos,null,"Pesquisa vazia","",tipo:"google"),"busca fixa precisa de tema");
            Recusa(()=>Navegador.Resultados("maps",new string('界',300)),"URL do Maps respeita limite depois de codificar Unicode");
            var json=new JavaScriptSerializer();
            var restaurados=json.Deserialize<Settings>(json.Serialize(new Settings {ComandosPastas=comandos}));
            Check(restaurados.ComandosPastas.Any(c=>c.Tipo=="youtube" && c.Termo=="Escrita criativa"),"tipo e assunto sobrevivem preferencias");
            var antigo=json.Deserialize<ComandoPasta>("{\"Frase\":\"Abrir projetos\",\"Caminho\":\"C:\\\\Projetos\"}");
            Check(antigo.Tipo=="pasta","cadastro antigo migra para pasta");
            Check(Navegador.Modelos().Length>=8,"modelos incluem diversas automacoes");
            var pedidos=new List<string>(); var fila=new PedidosWindows();
            Func<Client> cliente=()=>new Client("https://test.invalid","bella_"+new string('x',43),new ArquivosTestes.Servidor(pedidos,"Pesquisar sobre Escrita criativa",false));
            reply=fila.Enviar(null,new byte[] {1},local,cliente,null).GetAwaiter().GetResult();
            Check(reply.CodigoVoz=="pesquisa_aberta" && pedidos.Count==2 && pedidos[1].StartsWith("/api/bella/voz-local "),"voz pesquisa sem passar por Finances ou Rotinas");
            Check(!pedidos[1].Contains("Escrita") && !pedidos[1].Contains("https://"),"sintese nao recebe assunto nem URL");
            pedidos.Clear();
            cliente=()=>new Client("https://test.invalid","bella_"+new string('x',43),new ArquivosTestes.Servidor(pedidos,"Encontre dicas de narrativa na internet",false,Navegador.Padrao()[0].Id) {Assunto="dicas de narrativa"});
            reply=fila.Enviar("Encontre dicas de narrativa na internet",null,local,cliente,null).GetAwaiter().GetResult();
            Check(reply.CodigoVoz=="pesquisa_aberta" && abertos.Last().EndsWith("q=dicas%20de%20narrativa") && pedidos[0].StartsWith("/api/bella/interpretar-comando "),"IA retorna tipo registrado e tema para busca local");
            Check(!pedidos[0].Contains("https://calendar.google.com") && !pedidos[0].Contains("Caminho") && !pedidos[0].Contains("Termo"),"interpretacao nao recebe destinos nem configuracao fixa");
            int antesEscolha=abertos.Count;
            var padrao=Navegador.Padrao();
            reply=local.Interpretar(new InterpretacaoComando {candidatos=new[] {padrao[0].Id,padrao[1].Id},assunto="Escrita criativa"}).GetAwaiter().GetResult();
            Check(reply.CodigoVoz=="escolha" && abertos.Count==antesEscolha,"ambiguidade entre motores nao abre automaticamente");
            reply=local.Atender(reply.opcoes[1].comando);
            Check(reply.CodigoVoz=="pesquisa_aberta" && abertos.Last().Contains("youtube.com/results") && abertos.Last().EndsWith("Escrita%20criativa"),"escolha preserva assunto da IA");
        }
    }
}
