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
                Rede(files,permitida).GetAwaiter().GetResult();
            } finally {
                string full=Path.GetFullPath(raiz), baseFull=Path.GetFullPath(baseDirectory).TrimEnd(Path.DirectorySeparatorChar);
                if(!full.StartsWith(baseFull+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)) throw new Exception("Fixture fora da pasta de testes.");
                if(linkCriado && Directory.Exists(link)) Directory.Delete(link,false);
                if(Directory.Exists(full)) Directory.Delete(full,true);
            }
        }
        sealed class Servidor : HttpMessageHandler {
            readonly List<string> pedidos;
            public string Transcrito; public bool Falhar;
            public Servidor(List<string> calls,string heard,bool fail) { pedidos=calls; Transcrito=heard; Falhar=fail; }
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage r,CancellationToken token) {
                string body=await r.Content.ReadAsStringAsync(); pedidos.Add(r.RequestUri.AbsolutePath+" "+body);
                string json=r.RequestUri.AbsolutePath.EndsWith("transcrever")
                    ? new JavaScriptSerializer().Serialize(new { ouvido=Transcrito })
                    : new JavaScriptSerializer().Serialize(new { texto="Resposta Solo", falar="Pronto.", opcoes=new[] {new {numero=1, rotulo="Concluir", titulo="Missão"}} });
                return new HttpResponseMessage(Falhar ? HttpStatusCode.ServiceUnavailable : HttpStatusCode.OK) { Content=new StringContent(json,Encoding.UTF8,"application/json") };
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
