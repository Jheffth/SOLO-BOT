using System;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

namespace Bella {
    static class PerfilModelsTestes {
        static void Check(bool ok,string texto) { if(!ok) throw new Exception(texto); }
        sealed class Servidor : HttpMessageHandler {
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage r,CancellationToken token) {
                Check(r.RequestUri.AbsolutePath=="/api/bella/perfil","consulta usa rota própria");
                Check(r.Headers.Contains("X-Bella-Chave"),"perfil exige chave da própria conta");
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) {Content=new StringContent("{\"origem\":\"legado\",\"foto_id\":\"legado\"}")});
            }
        }
        public static void Run() {
            var r=new RetratoModels();
            Check(r.Remoto && r.Foto==null,"não mostra foto legada antes de conhecer a seleção");
            string a=Guid.NewGuid().ToString(),b=Guid.NewGuid().ToString();
            string foto="data:image/jpeg;base64,"+Convert.ToBase64String(new byte[] {255,216,255,224,0});
            r.Aplicar(new PerfilDesktop {origem="models",modelo_id=a,foto_id=a+":capa",foto=foto});
            r.Aplicar(new PerfilDesktop {origem="models",modelo_id=a,foto_id=a+":capa",inalterada=true});
            Check(r.Foto==foto,"consulta condicional preserva a mesma foto");
            r.Aplicar(new PerfilDesktop {origem="models",modelo_id=b,foto_id=b+":"});
            Check(r.Remoto && r.Foto==null && r.ModeloId==b,"modelo sem foto não herda foto da anterior");
            bool recusou=false;
            try { r.Aplicar(new PerfilDesktop {origem="models",modelo_id=a,foto_id=a+":capa",inalterada=true}); } catch { recusou=true; }
            Check(recusou && r.ModeloId==b,"resposta condicional de outro modelo é recusada");
            r.Aplicar(new PerfilDesktop {origem="legado"});
            Check(!r.Remoto && r.Foto==null,"voltar ao legado libera a foto local preservada");
            r.Limpar(); Check(r.FotoId==null && r.Remoto,"trocar acesso remove retrato da conta anterior");
            using(var c=new Client("https://test.invalid","bella_"+new string('x',43),new Servidor()))
                Check(c.Perfil("modelo:capa").GetAwaiter().GetResult().origem=="legado","cliente lê o perfil autenticado");
        }
    }
}
