using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;

namespace Bella {
    internal static class ArquivosTestes {
        static void Check(bool ok,string message) { if(!ok) throw new Exception("Arquivos: "+message); }
        static string Aspas(string p) { return "\""+p+"\""; }
        [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateSymbolicLink(string link,string target,int flags);
        public static void Run(string baseDirectory) {
            string raiz=Path.Combine(baseDirectory,"self-test-arquivos-"+Guid.NewGuid().ToString("N"));
            string permitida=Path.Combine(raiz,"permitida"), fora=Path.Combine(raiz,"fora"), destino=Path.Combine(permitida,"Destino"), lixeira=Path.Combine(raiz,"lixeira");
            string link=Path.Combine(permitida,"link-externo"); bool linkCriado=false;
            try {
                Directory.CreateDirectory(permitida); Directory.CreateDirectory(fora); Directory.CreateDirectory(destino); Directory.CreateDirectory(lixeira);
                string[] roots={permitida}; var abertos=new List<string>(); int reciclados=0;
                DateTime tempo=new DateTime(2026,10,13,12,0,0,DateTimeKind.Utc);
                var files=new Arquivos(()=>roots,p=> {
                    Check(Thread.CurrentThread.GetApartmentState()==ApartmentState.STA,"abertura usa STA como exige o Shell do Windows"); abertos.Add(p);
                },p=> {
                    Check(Thread.CurrentThread.GetApartmentState()==ApartmentState.STA,"Lixeira usa thread STA");
                    reciclados++; if(Directory.Exists(p)) Directory.Move(p,Path.Combine(lixeira,Path.GetFileName(p)));
                    else File.Move(p,Path.Combine(lixeira,Path.GetFileName(p)));
                },()=>tempo);
                string a=Path.Combine(permitida,"Relatório.pdf"), b=Path.Combine(destino,"Relatório.pdf");
                File.WriteAllText(a,"dados ficticios"); File.WriteAllText(b,"outros dados ficticios");
                Check(files.Atender("saldo")==null && files.Atender("criar uma missão organizar arquivos")==null,"pedidos Solo nao viram comandos locais");
                var r=files.Atender("Bella, por favor, pode criar uma nova pasta chamada Estudos em "+Aspas(permitida)+".");
                Check(r.CodigoVoz=="criada" && Directory.Exists(Path.Combine(permitida,"Estudos")),"cria pasta por frase natural");
                Check(files.Atender("/arquivos criar pasta Estudos em "+Aspas(permitida)).CodigoVoz=="existe","criar nao substitui item");
                Check(files.Atender("/arquivos criar pasta CON em "+Aspas(permitida)).CodigoVoz=="erro","nome reservado recusado");
                Check(files.Atender("/arquivos criar pasta Segredo em "+Aspas(fora)).CodigoVoz=="erro" && !Directory.Exists(Path.Combine(fora,"Segredo")),"nao cria fora da pasta permitida");
                File.WriteAllText(Path.Combine(fora,"externo.pdf"),"externo");
                Check(files.Atender("abrir arquivo "+Aspas(Path.Combine(fora,"externo.pdf"))).CodigoVoz=="erro" && abertos.Count==0,"nao abre caminho fora do acesso");
                Check(files.Atender("abrir arquivo "+Aspas(Path.Combine(permitida,"..","fora","externo.pdf"))).CodigoVoz=="erro","traversal nao escapa");
                File.WriteAllText(Path.Combine(permitida,"perigoso.cmd"),"fixture inerte");
                Check(files.Atender("abrir arquivo perigoso.cmd").CodigoVoz=="erro" && abertos.Count==0,"scripts nao sao executados");
                r=files.Atender("abrir arquivo relatorio.pdf");
                Check(r.CodigoVoz=="escolha" && r.opcoes.Length==2 && abertos.Count==0,"nomes iguais em subpastas exigem escolha");
                Check(files.Atender(r.opcoes[0].comando).CodigoVoz=="aberto" && abertos.Count==1,"botao local escolhe o caminho certo");
                Check(files.Atender(r.opcoes[0].comando).CodigoVoz=="expirou" && abertos.Count==1,"botao antigo nao executa duas vezes");
                r=files.Atender("/arquivos buscar arquivo relatorio em "+Aspas(permitida));
                Check(r.CodigoVoz=="busca" && r.opcoes.Length==2,"busca ignora acento e encontra subpastas");
                Check(files.Atender("dois").CodigoVoz=="aberto","escolha funciona por palavra falada");
                r=files.Atender("/arquivos listar "+Aspas(permitida));
                Check(r.CodigoVoz=="listagem" && r.opcoes.Length>0,"lista arquivos e pastas");
                files.Cancelar();
                // Referências diretas não dependem da varredura de outras pastas.
                string projetos=Path.Combine(permitida,"Projetos"), indisponivel=Path.Combine(raiz,"indisponivel");
                Directory.CreateDirectory(projetos); roots=new[] {permitida,indisponivel};
                foreach(string pedido in new[] {"Abra minha pasta de projetos.","Abra a minha pasta de Projetos.","Bella, abra minha pasta Projetos."}) {
                    r=files.Processar(pedido).GetAwaiter().GetResult();
                    Check(r.CodigoVoz=="aberto" && abertos.Last().Equals(projetos,StringComparison.OrdinalIgnoreCase),"abre projetos por frase natural sem busca ampla: "+pedido+" / "+r.texto);
                }
                roots=new[] {projetos,indisponivel};
                Check(files.Processar("Abra meus projetos.").GetAwaiter().GetResult().CodigoVoz=="aberto","nome natural de raiz configurada reconhecido como pedido local");
                string outroProjeto=Path.Combine(fora,"Projetos"); Directory.CreateDirectory(outroProjeto);
                roots=new[] {projetos,outroProjeto}; int antes=abertos.Count;
                r=files.Atender("abra minha pasta de projetos");
                Check(r.CodigoVoz=="escolha" && r.opcoes.Length==2 && abertos.Count==antes,"pastas configuradas com nomes iguais pedem escolha");
                roots=new[] {permitida,indisponivel};
                Check(files.Atender("listar minha pasta de projetos").CodigoVoz=="vazio","listagem usa a mesma referencia natural");
                File.WriteAllText(Path.Combine(permitida,"meu arquivo.txt"),"literal");
                Check(files.Processar("abrir arquivo \"meu arquivo.txt\"").GetAwaiter().GetResult().CodigoVoz=="aberto","aspas preservam possessivo literal no nome");
                r=files.Atender("abrir pasta desconhecida");
                Check(r.CodigoVoz=="erro" && r.texto.Contains("Configurações") && !r.texto.Contains("Não consegui consultar todas"),"busca parcial orienta adicionar acesso sem escolher automaticamente");
                r=files.Atender("abrir meus downloads");
                Check(r.CodigoVoz=="erro" && r.texto.Contains("não está nas pastas escolhidas"),"alias sem acesso nao cai numa varredura geral");
                string downloads=Arquivos.PastasPadrao().Last(p=>!p.Equals(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),StringComparison.OrdinalIgnoreCase)
                    && !p.Equals(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),StringComparison.OrdinalIgnoreCase));
                if(Directory.Exists(downloads)) {
                    // Só consulta a existência; opener simulado não abre nem lê arquivos pessoais.
                    var padrao=new Arquivos(()=>new[] {downloads,indisponivel},p=>abertos.Add(p));
                    foreach(string pedido in new[] {"Abra meus downloads.","Abra minha pasta de downloads.","Abra downloads."}) {
                        Check(padrao.Atender(pedido).CodigoVoz=="aberto" && abertos.Last()==downloads,"Downloads conhecido abre sem enumerar o conteudo: "+pedido);
                    }
                }
                roots=new[] {permitida};
                r=files.Atender("renomear arquivo "+Aspas(a)+" para final.pdf");
                Check(r.CodigoVoz=="confirmar_renomear" && File.Exists(a) && !File.Exists(Path.Combine(permitida,"final.pdf")),"renomear so prepara proposta");
                Check(files.Atender("não").CodigoVoz=="cancelado" && File.Exists(a),"nao cancela sem mexer");
                r=files.Atender("renomear arquivo "+Aspas(a)+" para final.pdf");
                Check(files.Atender("sim").CodigoVoz=="renomeado" && !File.Exists(a),"sim renomeia uma vez");
                string final=Path.Combine(permitida,"final.pdf");
                Check(files.Atender(r.opcoes[0].comando).CodigoVoz=="expirou" && File.Exists(final),"confirmacao consumida nao repete");
                r=files.Atender("mover arquivo "+Aspas(final)+" para "+Aspas(destino));
                Check(r.CodigoVoz=="confirmar_mover" && File.Exists(final),"mover exige confirmacao");
                Check(files.Atender("sim").CodigoVoz=="movido" && File.Exists(Path.Combine(destino,"final.pdf")),"move apos confirmar");
                Check(files.Atender("mover arquivo "+Aspas(b)+" para "+Aspas(destino)).CodigoVoz=="existe","mesmo destino nao move");
                File.WriteAllText(a,"nao substitua");
                Check(files.Atender("mover arquivo "+Aspas(a)+" para "+Aspas(destino)).CodigoVoz=="erro" && File.ReadAllText(a)=="nao substitua","colisao nunca substitui");
                r=files.Atender("renomear arquivo "+Aspas(a)+" para alterado.pdf");
                File.AppendAllText(a,"mudou");
                Check(files.Atender("sim").CodigoVoz=="erro" && File.Exists(a),"arquivo alterado exige novo pedido");
                r=files.Atender("excluir arquivo "+Aspas(a));
                Check(r.CodigoVoz=="confirmar_excluir" && reciclados==0 && File.Exists(a),"excluir so pergunta");
                tempo=tempo.AddMinutes(6);
                Check(files.Atender("sim").CodigoVoz=="expirou" && reciclados==0,"confirmacao expira em cinco minutos");
                r=files.Atender("excluir arquivo "+Aspas(a));
                roots=new string[0];
                Check(files.Atender("sim").CodigoVoz=="erro" && File.Exists(a),"acesso removido e reconferido na confirmacao");
                roots=new[] {permitida};
                r=files.Atender("excluir arquivo "+Aspas(a));
                Check(files.Atender(r.opcoes[0].comando).CodigoVoz=="excluido" && reciclados==1 && !File.Exists(a),"exclusao usa provedor de lixeira apos confirmar");
                Check(files.Atender("excluir pasta "+Aspas(permitida)).CodigoVoz=="erro","pasta principal de acesso nao e excluida");
                linkCriado=CreateSymbolicLink(link,fora,3);
                if(linkCriado) {
                    Check(files.Atender("abrir arquivo "+Aspas(Path.Combine(link,"externo.pdf"))).CodigoVoz=="erro","link nao escapa da pasta escolhida");
                    r=files.Atender("/arquivos buscar arquivo externo em "+Aspas(permitida));
                    Check(r.CodigoVoz=="vazio","busca nao segue links");
                }
                Comandos(files,permitida,fora,link,linkCriado);
                Rede(files,permitida).GetAwaiter().GetResult();
                Latencia(files,permitida).GetAwaiter().GetResult();
            } finally {
                string full=Path.GetFullPath(raiz), baseFull=Path.GetFullPath(baseDirectory).TrimEnd(Path.DirectorySeparatorChar);
                if(!full.StartsWith(baseFull+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)) throw new Exception("Fixture fora da pasta de testes.");
                if(linkCriado && Directory.Exists(link)) Directory.Delete(link,false);
                if(Directory.Exists(full)) Directory.Delete(full,true);
            }
        }
        static void Recusa(Action acao,string mensagem) {
            bool recusou=false; try { acao(); } catch(InvalidOperationException) { recusou=true; }
            Check(recusou,mensagem);
        }
        static void Comandos(Arquivos files,string permitida,string fora,string link,bool linkCriado) {
            var abertos=new List<string>();
            var comandos=ComandosPastas.Atualizar(null,null,"Abrir minha pasta de Projetos",fora);
            string id=comandos[0].Id;
            var local=new Arquivos(()=>new[] {permitida},p=>abertos.Add(p),commands:()=>comandos);
            foreach(string frase in new[] {"Abrir minha pasta de Projetos","Abra minha pasta de projetos.","Bella, por favor, abra minha pasta de Projetos!",
                "Quero que abra a minha pasta de projetos.","Eu gostaria que você abrisse a minha pasta de projetos", "Gostaria de abrir a minha pasta de projetos, por favor."})
                Check(local.Processar(frase).GetAwaiter().GetResult().CodigoVoz=="aberto" && abertos.Last()==fora,"comando personalizado abre diretamente fora das raizes de busca: "+frase);
            Check(local.Atender("excluir pasta "+Aspas(fora)).CodigoVoz=="erro","cadastro de abertura nao concede acesso para exclusao");
            Check(local.Atender("listar "+Aspas(fora)).CodigoVoz=="erro","cadastro de abertura nao amplia raizes de busca");
            Recusa(()=>ComandosPastas.Atualizar(comandos,null,"Abra minha pasta de projetos!",permitida),"frases equivalentes nao podem ter destinos diferentes");
            Recusa(()=>ComandosPastas.Atualizar(comandos,null,"sim",permitida),"comando nao captura confirmacao");
            Recusa(()=>ComandosPastas.Atualizar(comandos,null,"dois",permitida),"comando nao captura escolha numerica");
            Recusa(()=>ComandosPastas.Atualizar(comandos,null,"/saldo",permitida),"comando nao captura comando com barra");
            Recusa(()=>ComandosPastas.Atualizar(comandos,null,"Pasta invalida",Path.Combine(fora,"inexistente")),"caminho inexistente nao e salvo");
            Recusa(()=>ComandosPastas.Atualizar(comandos,null,"Abrir arquivo",Path.Combine(permitida,"perigoso.cmd")),"somente pastas podem ser cadastradas");
            if(linkCriado) Recusa(()=>ComandosPastas.Atualizar(comandos,null,"Abrir atalho",link),"link nao e salvo como pasta");
            var anterior=comandos;
            comandos=ComandosPastas.Atualizar(comandos,id,"Hora de programar",permitida);
            Check(anterior[0].Frase=="Abrir minha pasta de Projetos" && comandos.Length==1 && comandos[0].Id==id,"edicao preserva identidade e nao altera configuracao anterior");
            Check(local.Processar("Hora de programar").GetAwaiter().GetResult().CodigoVoz=="aberto" && abertos.Last()==permitida,"edicao muda frase e caminho imediatamente");
            var serializer=new JavaScriptSerializer();
            var config=serializer.Deserialize<Settings>(serializer.Serialize(new Settings {ComandosPastas=comandos}));
            Check(config.ComandosPastas.Length==1 && config.ComandosPastas[0].Caminho==permitida && config.ComandosPastas[0].Frase=="Hora de programar","comandos sobrevivem serializacao das preferencias");
            Check(serializer.Deserialize<Settings>("{}").ComandosPastas.Length==0,"configuracao antiga inicia sem comandos");
            comandos=ComandosPastas.Atualizar(comandos,id,null,null,true);
            Check(local.Atender("Hora de programar")==null && Directory.Exists(permitida),"remover so apaga associacao, preservando a pasta");
            Recusa(()=>ComandosPastas.Atualizar(comandos,id,"Frase antiga",permitida),"edicao antiga nao recria comando removido");
            string temporaria=Path.Combine(permitida,"comando-temporario"); Directory.CreateDirectory(temporaria);
            comandos=ComandosPastas.Atualizar(comandos,null,"Pasta temporaria",temporaria);
            Directory.Delete(temporaria); int antes=abertos.Count;
            Check(local.Atender("Pasta temporaria").CodigoVoz=="erro" && abertos.Count==antes,"pasta e reconferida a cada abertura");
            comandos=ComandosPastas.Atualizar(null,null,"Hora de programar",fora);
            var pedidos=new List<string>(); var fila=new PedidosWindows();
            Func<Client> cliente=()=>new Client("https://test.invalid","bella_"+new string('x',43),new Servidor(pedidos,"Hora de programar",false));
            var r=fila.Enviar(null,new byte[] {1},local,cliente,null).GetAwaiter().GetResult();
            Check(r.CodigoVoz=="aberto" && abertos.Last()==fora && pedidos.Count==2 && pedidos[1].StartsWith("/api/bella/voz-local "),"comando personalizado por voz executa localmente sem passar pelo hub");
            Check(!pedidos[1].Contains(fora) && !pedidos[1].Contains("Hora de programar"),"sintese nao recebe cadastro nem caminho");
            pedidos.Clear(); string livre="Leve-me até a pasta onde desenvolvo meus projetos.";
            Func<Client> ia=()=>new Client("https://test.invalid","bella_"+new string('x',43),new Servidor(pedidos,livre,false,comandos[0].Id));
            r=fila.Enviar(livre,null,local,ia,null).GetAwaiter().GetResult();
            Check(r.CodigoVoz=="aberto" && abertos.Last()==fora && pedidos.Count==2 && pedidos[0].StartsWith("/api/bella/interpretar-comando "),"frase livre consulta IA antes do hub e abre comando validado");
            Check(!pedidos[0].Contains(fora.Replace("\\","\\\\")) && !pedidos[0].Contains("Caminho") && pedidos[0].Contains("Hora de programar"),"interpretacao recebe somente frase e id, sem caminho cadastrado");
            pedidos.Clear(); int quantidade=abertos.Count;
            Func<Client> falhaIa=()=>new Client("https://test.invalid","bella_"+new string('x',43),new Servidor(pedidos,livre,false,null,true));
            r=fila.Enviar(livre,null,local,falhaIa,null).GetAwaiter().GetResult();
            Check(r.CodigoVoz=="escolha" && abertos.Count==quantidade && !pedidos.Any(p=>p.StartsWith("/api/bella/mensagem ")),"falha da IA pergunta localmente e nao envia pedido ao Finances");
            Check(fila.Enviar(r.opcoes[0].comando,null,local,ia,null).GetAwaiter().GetResult().CodigoVoz=="aberto","escolha local abre apos falha da IA");
            pedidos.Clear(); quantidade=abertos.Count;
            Func<Client> inventada=()=>new Client("https://test.invalid","bella_"+new string('x',43),new Servidor(pedidos,livre,false,new string('f',32)));
            r=fila.Enviar(null,new byte[] {1},local,inventada,null).GetAwaiter().GetResult();
            Check(r.CodigoVoz=="escolha" && abertos.Count==quantidade && pedidos.Count==3 && !pedidos.Any(p=>p.StartsWith("/api/bella/mensagem ")),"id desconhecido da IA por voz nao executa nem cai no Finances");
            pedidos.Clear();
            r=fila.Enviar("Não abra a pasta de projetos",null,local,ia,null).GetAwaiter().GetResult();
            Check(r.CodigoVoz=="cancelado" && abertos.Count==quantidade && !pedidos.Any(p=>p.StartsWith("/api/bella/interpretar-comando ")),"pedido negado nao abre pasta");
            pedidos.Clear();
            r=fila.Enviar("Quero ver meu saldo",null,local,ia,null).GetAwaiter().GetResult();
            Check(pedidos.Count==1 && pedidos[0].StartsWith("/api/bella/mensagem ") && pedidos[0].Contains("Quero ver meu saldo"),"consulta financeira preserva texto e nao usa interpretacao local");
            pedidos.Clear(); bool continuar=true, cancelou=false; quantidade=abertos.Count;
            Func<Client> cancelando=()=>new Client("https://test.invalid","bella_"+new string('x',43),new Servidor(pedidos,livre,false,comandos[0].Id) {AoInterpretar=()=>continuar=false});
            try { fila.Enviar(livre,null,local,cancelando,null,()=>continuar).GetAwaiter().GetResult(); }
            catch(OperationCanceledException) { cancelou=true; }
            Check(cancelou && abertos.Count==quantidade,"encerrar durante interpretacao nao abre pasta depois");
        }
        internal sealed class Servidor : HttpMessageHandler {
            readonly List<string> pedidos;
            public string Transcrito, Interpretado; public bool Falhar, FalharIA;
            public Action AoInterpretar;
            public string Assunto;
            public Servidor(List<string> calls,string heard,bool fail,string command=null,bool failIA=false) { pedidos=calls; Transcrito=heard; Falhar=fail; Interpretado=command; FalharIA=failIA; }
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage r,CancellationToken token) {
                string body=await r.Content.ReadAsStringAsync(); pedidos.Add(r.RequestUri.AbsolutePath+" "+body);
                bool interpretar=r.RequestUri.AbsolutePath.EndsWith("interpretar-comando");
                if(interpretar && AoInterpretar!=null) AoInterpretar();
                string json=interpretar ? new JavaScriptSerializer().Serialize(new {comando_id=Interpretado,candidatos=new string[0],assunto=Assunto}) : r.RequestUri.AbsolutePath.EndsWith("transcrever")
                    ? new JavaScriptSerializer().Serialize(new { ouvido=Transcrito })
                    : new JavaScriptSerializer().Serialize(new { texto="Resposta Solo", falar="Pronto.", opcoes=new[] {new {numero=1, rotulo="Concluir", titulo="Missão"}} });
                return new HttpResponseMessage(Falhar || (interpretar && FalharIA) ? HttpStatusCode.ServiceUnavailable : HttpStatusCode.OK) { Content=new StringContent(json,Encoding.UTF8,"application/json") };
            }
        }
        sealed class VozLenta : HttpMessageHandler {
            public readonly TaskCompletionSource<bool> Entrou=new TaskCompletionSource<bool>();
            public readonly TaskCompletionSource<bool> Liberar=new TaskCompletionSource<bool>();
            public int Operacoes;
            public bool Falhar;
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage r,CancellationToken token) {
                bool mensagem=r.RequestUri.AbsolutePath.EndsWith("/mensagem");
                if(mensagem) {
                    Operacoes++;
                    string corpo=await r.Content.ReadAsStringAsync();
                    Check(corpo.Contains("\"voz_separada\":true"),"cliente pede resultado antes da voz");
                } else {
                    Entrou.TrySetResult(true);
                    await Liberar.Task;
                }
                return new HttpResponseMessage(!mensagem && Falhar ? HttpStatusCode.ServiceUnavailable : HttpStatusCode.OK) {
                    Content=new StringContent(mensagem
                        ? "{\"texto\":\"Saldo pronto\",\"falar\":\"Seu saldo está na tela.\",\"voz_id\":\"00000000-0000-0000-0000-000000000001\",\"opcoes\":[]}"
                        : "{\"falar\":\"Pronto.\",\"audio_base64\":\"SUQz\",\"mime\":\"audio/mpeg\"}",Encoding.UTF8,"application/json") };
            }
            protected override void Dispose(bool disposing) { } // Compartilhado entre os clientes deste teste.
        }
        static async Task Latencia(Arquivos files,string pasta) {
            foreach(bool local in new[] {false,true}) {
                foreach(bool falhar in new[] {false,true}) {
                    var servidor=new VozLenta {Falhar=falhar}; var fila=new PedidosWindows();
                    bool exibido=false;
                    var envio=fila.Enviar(local ? "/arquivos listar "+Aspas(pasta) : "saldo de hoje",null,files,
                        ()=>new Client("https://test.invalid","bella_"+new string('x',43),servidor),null,null,
                        r=> { exibido=true; Check(!servidor.Entrou.Task.IsCompleted,"resultado aparece antes da consulta de voz"); });
                    try {
                        Check(await Task.WhenAny(servidor.Entrou.Task,Task.Delay(5000))==servidor.Entrou.Task,"chegou ao pedido de voz");
                        Check(exibido && !envio.IsCompleted,"voz lenta nao esconde o resultado local ou financeiro");
                    } finally { servidor.Liberar.TrySetResult(true); }
                    var resposta=await envio;
                    Check(servidor.Operacoes==(local ? 0 : 1),"voz nao reenvia a operação");
                    Check(!String.IsNullOrEmpty(resposta.falar),"falha da voz mantém fala do Windows");
                    Check(falhar || resposta.audio_base64=="SUQz","voz escolhida continua disponível");
                }
            }
        }
        static async Task Rede(Arquivos files,string pasta) {
            var fila=new PedidosWindows();
            var pedidos=new List<string>(); string heard="Bella, criar pasta Só local em "+Aspas(pasta);
            Func<Client> cliente=()=>new Client("https://test.invalid","bella_"+new string('x',43),new Servidor(pedidos,heard,false));
            string ouvido=null;
            var r=await fila.Enviar(null,new byte[] {1,2,3},files,cliente,t=>ouvido=t);
            Check(r.CodigoVoz=="criada" && ouvido==heard && Directory.Exists(Path.Combine(pasta,"Só local")),"voz transcreve antes de agir localmente");
            Check(pedidos.Count==2 && pedidos[0].StartsWith("/api/bella/transcrever ") && pedidos[1].StartsWith("/api/bella/voz-local "),"pedido local nunca chega ao roteador Solo");
            Check(!pedidos[1].Contains(pasta) && !pedidos[1].Contains("Só local"),"resposta falada nao envia nomes nem caminhos");
            pedidos.Clear(); heard="Recebi R$ 92,60 na conta Uber.";
            r=await fila.Enviar(null,new byte[] {1,2,3},files,cliente,t=>ouvido=t);
            Check(pedidos.Count==2 && pedidos[1].StartsWith("/api/bella/mensagem ") && pedidos[1].Contains("92,60") && pedidos[1].Contains("\"via_audio\":true"),"pedido Solo segue uma vez com valor e origem por voz");
            string escolhaSolo=r.opcoes[0].comando;
            pedidos.Clear();
            r=await fila.Enviar("/arquivos listar "+Aspas(pasta),null,files,cliente,null);
            Check(pedidos.Count==1 && pedidos[0].StartsWith("/api/bella/voz-local "),"texto de arquivos tambem fica local");
            string proteger=Path.Combine(pasta,"nao-excluir.txt"); File.WriteAllText(proteger,"fixture");
            r=await fila.Enviar("excluir arquivo "+Aspas(proteger),null,files,cliente,null);
            Check(r.CodigoVoz=="confirmar_excluir","proposta local pronta para teste de escolha antiga");
            pedidos.Clear(); r=await fila.Enviar(escolhaSolo,null,files,cliente,null);
            Check(r.CodigoVoz=="expirou" && File.Exists(proteger) && pedidos.Count==0,"botao antigo do Solo nao confirma exclusao local");
            r=await fila.Enviar("sim",null,files,cliente,null);
            Check(r.CodigoVoz=="expirou" && pedidos.Count==0 && File.Exists(proteger),"sim depois de resposta local nao confirma pedido antigo do Solo");
            pedidos.Clear(); files.Cancelar();
            bool falhou=false;
            try { await fila.Enviar(null,new byte[] {1},files,()=>new Client("https://test.invalid","bella_"+new string('x',43),new Servidor(pedidos,"excluir arquivo teste.txt",true)),null); }
            catch(InvalidOperationException) { falhou=true; }
            Check(falhou && pedidos.Count==1 && pedidos[0].StartsWith("/api/bella/transcrever "),"falha de transcricao nao executa nada");
        }
    }
}
