using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
namespace Bella {
    static class AnexoTestes {
        sealed class Rede : HttpMessageHandler {
            readonly List<string> caminhos;
            readonly List<Dictionary<string,object>> corpos;
            readonly bool falhar;
            public Rede(List<string> p,List<Dictionary<string,object>> c,bool f) {caminhos=p;corpos=c;falhar=f;}
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage r,CancellationToken t) {
                caminhos.Add(r.RequestUri.AbsolutePath);
                corpos.Add(new JavaScriptSerializer {MaxJsonLength=16*1024*1024}.Deserialize<Dictionary<string,object>>(await r.Content.ReadAsStringAsync()));
                if(falhar) throw new HttpRequestException("falha simulada");
                return new HttpResponseMessage(HttpStatusCode.OK) {Content=new StringContent("{\"texto\":\"Prompt de roupa pronto\",\"opcoes\":[]}",Encoding.UTF8,"application/json")};
            }
        }
        static void Check(bool ok,string m) {if(!ok) throw new Exception("Anexo: "+m);}
        public static void Run() {Testar().GetAwaiter().GetResult();}
        static async Task Testar() {
            var caminhos=new List<string>(); var corpos=new List<Dictionary<string,object>>(); bool falhar=false;
            Func<Client> cliente=()=>new Client("https://test.invalid","bella_"+new string('x',43),new Rede(caminhos,corpos,falhar));
            var arquivos=new Arquivos(()=>new string[0],p=>{throw new Exception("Anexo abriu arquivo local");});
            var pedidos=new PedidosWindows();
            string imagem="data:image/jpeg;base64,"+new string('A',2500000);
            foreach(var texto in new[] {"abra a pasta banheiro", "gere uma imagem de vestido", "1"}) {
                pedidos.ImagemRef=imagem;
                await pedidos.Enviar(texto,null,arquivos,cliente,null).ConfigureAwait(false);
                Check(caminhos[caminhos.Count-1]=="/api/bella/conversa","anexo tem prioridade sobre comandos");
                Check((string)corpos[corpos.Count-1]["imagem_base64"]==imagem.Substring(23),"imagem acima de 2 MB serializada inteira");
                Check(pedidos.ImagemRef==null,"referência consumida");
            }
            await pedidos.Enviar("consulta",null,arquivos,cliente,null).ConfigureAwait(false);
            Check(!corpos[corpos.Count-1].ContainsKey("imagem_base64"),"pedido seguinte sem imagem");
            pedidos.ImagemRef=imagem; falhar=true; bool erro=false;
            try {await pedidos.Enviar("prompt banheiro",null,arquivos,cliente,null).ConfigureAwait(false);} catch(InvalidOperationException) {erro=true;}
            Check(erro && pedidos.ImagemRef==null,"falha de rede descarta anexo");
        }
    }
}
