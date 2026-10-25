using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;

namespace Bella {
    internal static class ImagensTestes {
        static void Check(bool ok,string texto) {if(!ok) throw new Exception("Imagens: "+texto);}
        sealed class Rede : HttpMessageHandler {
            public string Imagem; public bool Falhar,Ausente; public List<string> Rotas=new List<string>();
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage r,CancellationToken token) {
                var corpo=await r.Content.ReadAsStringAsync(); string rota=r.RequestUri.AbsolutePath; Rotas.Add(rota);
                object saida;
                if(rota.EndsWith("/transcrever")) saida=new {ouvido="Bella, gere uma imagem de uma cidade"};
                else if(rota.EndsWith("/imagem")) {
                    var d=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(corpo);
                    Guid id; Check(Guid.TryParse((string)d["pedido_id"],out id) && (string)d["prompt"]=="uma cidade","pedido contém ID e descrição");
                    if(Ausente) return new HttpResponseMessage(HttpStatusCode.NotFound) {Content=new StringContent("{\"detail\":\"Not Found\"}")};
                    if(Falhar) return new HttpResponseMessage(HttpStatusCode.BadGateway) {Content=new StringContent("{\"detail\":\"Grok indisponível\"}")};
                    saida=new {texto="Imagem pronta. Veja no painel Imagens.",imagem_base64=Imagem,imagem_mime="image/png"};
                } else {
                    Check(rota.EndsWith("/voz-local") && corpo.Contains("imagem_pronta"),"imagem não cai em Word ou sistemas");
                    saida=new {falar="A imagem está no painel.",audio_base64="SUQz",mime="audio/mpeg"};
                }
                return new HttpResponseMessage(HttpStatusCode.OK) {Content=new StringContent(new JavaScriptSerializer {MaxJsonLength=16*1024*1024}.Serialize(saida),Encoding.UTF8,"application/json")};
            }
        }
        public static void Run(string baseDirectory) {
            string codigo;
            using(var bitmap=new Bitmap(40,25)) using(var buffer=new MemoryStream()) {bitmap.Save(buffer,ImageFormat.Png); codigo=Convert.ToBase64String(buffer.ToArray());}
            string prompt;
            Check(PedidosWindows.PedidoImagem("Bella, gere uma imagem de uma cidade",out prompt) && prompt=="uma cidade","pedido natural reconhecido");
            Check(PedidosWindows.PedidoImagem("/imagem uma cidade",out prompt) && prompt=="uma cidade","pedido da aba reconhecido");
            Check(!PedidosWindows.PedidoImagem("Não gere uma imagem de cidade",out prompt),"negação não gera");
            foreach(bool audio in new[] {false,true}) {
                var rede=new Rede {Imagem=codigo}; var fila=new PedidosWindows(); var estados=new List<bool>(); int finais=0;
                fila.GerandoImagem+=(ativa,erro)=>estados.Add(ativa);
                var r=fila.Enviar(audio ? null : "/imagem uma cidade",audio ? new byte[] {1} : null,new Arquivos(()=>new string[0]),
                    ()=>new Client("https://test.invalid","bella_"+new string('x',43),rede),null,null,x=>finais++).GetAwaiter().GetResult();
                Check(finais==1 && r.imagem_base64==codigo && r.audio_base64=="SUQz" && estados.SequenceEqual(new[] {true,false}),"um resultado e progresso concluído com voz configurada");
                Check(rede.Rotas.Count==(audio ? 3 : 2) && rede.Rotas.Count(x=>x.EndsWith("/imagem"))==1,"sem geração duplicada por texto ou voz");
            }
            var falha=new Rede {Falhar=true}; var envio=new PedidosWindows(); string erroFinal=null;
            envio.GerandoImagem+=(ativa,erro)=> {if(!ativa) erroFinal=erro;};
            bool falhou=false;
            try {envio.Enviar("/imagem uma cidade",null,new Arquivos(()=>new string[0]),()=>new Client("https://test.invalid","bella_"+new string('x',43),falha),null).GetAwaiter().GetResult();} catch(InvalidOperationException) {falhou=true;}
            Check(falhou && erroFinal=="Grok indisponível" && falha.Rotas.Count==1,"erro vai ao painel sem reenviar ou cair em outro provedor");
            var antigo=new Rede {Ausente=true};
            string aviso=null;
            try {new PedidosWindows().Enviar("/imagem uma cidade",null,new Arquivos(()=>new string[0]),()=>new Client("https://test.invalid","bella_"+new string('x',43),antigo),null).GetAwaiter().GetResult();}
            catch(InvalidOperationException e) {aviso=e.Message;}
            Check(aviso!=null && aviso.Contains("Publique o backend") && !aviso.Contains("Not Found") && antigo.Rotas.Count==1,"servidor antigo informa atualização necessária e não reenvia imagem");
            string pasta=Path.Combine(baseDirectory,"self-test-imagens-"+Guid.NewGuid().ToString("N"));
            try {
                var galeria=new GaleriaImagens(pasta);
                Check(galeria.Listar().Length==0,"galeria vazia não cria arquivos");
                for(int i=0;i<7;i++) galeria.Guardar(new Reply {imagem_base64=codigo,imagem_mime="image/png"});
                var itens=galeria.Listar();
                Check(itens.Length==6 && Directory.GetFiles(pasta).Length==6,"galeria limitada a seis originais");
                Check(File.ReadAllBytes(galeria.Caminho(itens[0].Id)).SequenceEqual(Convert.FromBase64String(codigo)),"exportação conserva original");
                Check(itens.All(x=>x.Previa.StartsWith("data:image/jpeg;base64,")),"interface recebe somente prévias reduzidas");
                bool recusou=false; try {galeria.Caminho("../acesso.dat");} catch(InvalidOperationException) {recusou=true;}
                Check(recusou,"interface não escolhe caminho para leitura");
                Check(new GaleriaImagens(pasta).Listar().Length==6,"galeria permanece entre sessões");
                File.WriteAllText(Path.Combine(pasta,"usuario.txt"),"preservar");
                galeria.Guardar(new Reply {imagem_base64=codigo,imagem_mime="image/png"});
                Check(File.Exists(Path.Combine(pasta,"usuario.txt")),"limpeza ignora outros arquivos");
            } finally {
                string alvo=Path.GetFullPath(pasta),raiz=Path.GetFullPath(baseDirectory).TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar;
                if(!alvo.StartsWith(raiz,StringComparison.OrdinalIgnoreCase)) throw new Exception("Fixture fora da raiz");
                if(Directory.Exists(pasta)) Directory.Delete(pasta,true);
            }
        }
    }
}
