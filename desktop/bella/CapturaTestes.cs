using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;

namespace Bella {
    // O recorte em si precisa de tela e mouse; aqui vai tudo o que dá para conferir sem eles.
    internal static class CapturaTestes {
        static void Check(bool ok,string texto) { if(!ok) throw new Exception("Recorte de tela: "+texto); }
        public static void Run() {
            // Três monitores em pixels reais, como no Windows com escalas diferentes:
            // 4K a 150% à esquerda, 1080p a 100% no meio, 1440p a 125% à direita e mais alto.
            var monitores=new List<Rectangle> { new Rectangle(-3840,0,3840,2160), new Rectangle(0,0,1920,1080), new Rectangle(1920,-200,2560,1440) };
            var virt=CapturaTela.Uniao(monitores);
            Check(virt==Rectangle.FromLTRB(-3840,-200,4480,2160),"área virtual cobre os três monitores");
            Check(CapturaTela.MonitorEm(monitores,new Point(-10,500))==monitores[0],"ponto no monitor da esquerda");
            Check(CapturaTela.MonitorEm(monitores,new Point(2000,-150))==monitores[2],"ponto no monitor mais alto");
            Check(CapturaTela.MonitorEm(monitores,new Point(1000,1500))==monitores[1],"ponto fora de todos vai ao mais próximo");
            Check(CapturaTela.Normalizar(new Point(100,90),new Point(-50,10))==Rectangle.FromLTRB(-50,10,100,90),"arrastar para trás também recorta");
            Check(CapturaTela.Normalizar(new Point(-100,100),new Point(2100,300))==Rectangle.FromLTRB(-100,100,2100,300),"seleção atravessa monitores");
            var janelas=new List<Rectangle> { new Rectangle(100,100,400,300), new Rectangle(50,50,1000,800) };   // de cima para baixo
            Check(CapturaTela.JanelaEm(janelas,new Point(200,200))==janelas[0],"clique pega a janela de cima");
            Check(CapturaTela.JanelaEm(janelas,new Point(900,700))==janelas[1],"clique pega a janela de baixo onde a de cima não está");
            Check(!CapturaTela.JanelaEm(janelas,new Point(1500,900)).HasValue,"fora das janelas não há destaque");

            // O que vai ao chat: JPEG de verdade, até 1280 px, proporção mantida.
            using(var grande=new Bitmap(3000,1000)) {
                using(var g=Graphics.FromImage(grande)) g.Clear(Color.MediumPurple);
                var url=CapturaTela.ParaEnviar(grande);
                Check(url.StartsWith("data:image/jpeg;base64,"),"envio é JPEG");
                var bytes=Convert.FromBase64String(url.Substring("data:image/jpeg;base64,".Length));
                Check(Foto.Tipo(bytes)=="jpeg","bytes são JPEG");
                using(var lido=new Bitmap(new MemoryStream(bytes))) Check(lido.Width==1280 && Math.Abs(lido.Height-427)<=1,"reduz para 1280 px mantendo a proporção");
            }
            using(var pequeno=new Bitmap(300,200)) {
                var bytes=Convert.FromBase64String(CapturaTela.ParaEnviar(pequeno).Substring(23));
                using(var lido=new Bitmap(new MemoryStream(bytes))) Check(lido.Width==300 && lido.Height==200,"recorte pequeno não é ampliado");
            }

            // Frases que pedem o recorte (só a frase inteira, para não disparar por engano).
            foreach(var sim in new[] { "recorta a tela","Bella, recortar tela","captura a tela","tira um print","faz um print da tela","Bella, por favor, captura minha tela","/recortar","print" })
                Check(CapturaTela.Pedido(sim),"entende: "+sim);
            foreach(var nao in new[] { "crie um prompt com essa referência","recorte de cabelo curto","abre a pasta de prints","como capturar um pokémon","imprime o documento" })
                Check(!CapturaTela.Pedido(nao),"não confunde: "+nao);
        }
    }
}
