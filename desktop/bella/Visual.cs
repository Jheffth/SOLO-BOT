using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace Bella {
    // O acabamento do Windows: barra de título escura, cantos arredondados,
    // ícones desenhados (o orbe da marca, com a cor do estado) e o menu escuro
    // do ícone perto do relógio. Nada de arquivo de imagem no pacote.
    static class Visual {
        [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd,int attr,ref int value,int size);

        public static readonly Color Fundo=Color.FromArgb(14,15,24);
        static readonly Color Violeta=Color.FromArgb(139,92,246), Ciano=Color.FromArgb(34,211,238);

        static int Cor(Color c) { return c.R | (c.G<<8) | (c.B<<16); }       // COLORREF = 0x00BBGGRR
        static void Atributo(IntPtr h,int attr,int valor) { try { DwmSetWindowAttribute(h,attr,ref valor,4); } catch { } }

        /// <summary>Barra de título escura (Windows 10 20H1+) com a cor do fundo da Bella (Windows 11).</summary>
        public static void JanelaEscura(Form f) {
            var h=f.Handle;
            Atributo(h,20,1); Atributo(h,19,1);                 // DWMWA_USE_IMMERSIVE_DARK_MODE (novo e antigo)
            Atributo(h,35,Cor(Fundo));                           // DWMWA_CAPTION_COLOR
            Atributo(h,34,Cor(Color.FromArgb(38,40,62)));        // DWMWA_BORDER_COLOR
            Atributo(h,36,Cor(Color.FromArgb(236,237,247)));     // DWMWA_TEXT_COLOR
        }
        /// <summary>Escala da tela (1 = 100%, 1.5 = 150%). O app é "DPI aware": medidas em pixels reais.</summary>
        public static float Escala() {
            try { using(var g=Graphics.FromHwnd(IntPtr.Zero)) return Math.Max(1f,g.DpiX/96f); } catch { return 1f; }
        }
        public static Size Medida(int largura,int altura) { var k=Escala(); return new Size((int)(largura*k),(int)(altura*k)); }

        /// <summary>Cantos arredondados do Windows 11 (sem efeito no 10).</summary>
        public static void CantosRedondos(Form f) { Atributo(f.Handle,33,2); }

        // ── Ícones ───────────────────────────────────────────────────
        static readonly Dictionary<string,Icon> icones=new Dictionary<string,Icon>();
        public static Color CorDoModo(Capture.Mode? modo) {
            if(modo==null) return Color.Empty;
            switch(modo.Value) {
                case Capture.Mode.Listening: return Color.FromArgb(52,211,153);
                case Capture.Mode.Recording: return Color.FromArgb(34,211,238);
                case Capture.Mode.Processing: return Color.FromArgb(251,191,36);
                case Capture.Mode.Greeting:
                case Capture.Mode.Speaking: return Color.FromArgb(196,181,253);
                default: return Color.FromArgb(107,110,138);
            }
        }
        /// <summary>O orbe da Bella; com modo, ganha o ponto colorido do estado (para o ícone perto do relógio).</summary>
        public static Icon Icone(Capture.Mode? modo,int lado=32) {
            string chave=(modo==null?"janela":modo.Value.ToString())+lado;
            Icon pronto;
            if(icones.TryGetValue(chave,out pronto)) return pronto;
            using(var bmp=new Bitmap(lado,lado)) {
                using(var g=Graphics.FromImage(bmp)) {
                    g.SmoothingMode=SmoothingMode.AntiAlias; g.Clear(Color.Transparent);
                    float m=lado*.06f, d=lado-2*m;
                    var corpo=new RectangleF(m,m,d,d);
                    using(var pincel=new LinearGradientBrush(corpo,Violeta,Ciano,45f)) g.FillEllipse(pincel,corpo);
                    using(var caminho=new GraphicsPath()) {
                        caminho.AddEllipse(m+d*.12f,m+d*.08f,d*.5f,d*.44f);
                        using(var brilho=new PathGradientBrush(caminho)) {
                            brilho.CenterColor=Color.FromArgb(170,255,255,255); brilho.SurroundColors=new[] { Color.FromArgb(0,255,255,255) };
                            g.FillPath(brilho,caminho);
                        }
                    }
                    if(modo!=null) {
                        float r=lado*.42f, x=lado-r-lado*.01f, y=lado-r-lado*.01f;
                        using(var borda=new SolidBrush(Fundo)) g.FillEllipse(borda,x-lado*.06f,y-lado*.06f,r+lado*.12f,r+lado*.12f);
                        using(var ponto=new SolidBrush(CorDoModo(modo))) g.FillEllipse(ponto,x,y,r,r);
                    }
                }
                // O Icon guarda o HICON; fica em cache pelo tempo de vida do app (são poucos).
                pronto=Icon.FromHandle(bmp.GetHicon());
            }
            icones[chave]=pronto;
            return pronto;
        }

        // ── Menu escuro do ícone ─────────────────────────────────────
        public static ToolStripRenderer MenuEscuro() { return new Renderizador(); }
        sealed class Renderizador : ToolStripProfessionalRenderer {
            public Renderizador() : base(new Cores()) { RoundedEdges=false; }
            protected override void OnRenderItemText(ToolStripItemTextRenderEventArgs e) {
                e.TextColor=e.Item.Enabled?Color.FromArgb(236,237,247):Color.FromArgb(107,110,138); base.OnRenderItemText(e);
            }
        }
        sealed class Cores : ProfessionalColorTable {
            static readonly Color fundo=Color.FromArgb(22,23,39), sel=Color.FromArgb(39,41,68), borda=Color.FromArgb(48,50,78);
            public override Color ToolStripDropDownBackground { get { return fundo; } }
            public override Color ImageMarginGradientBegin { get { return fundo; } }
            public override Color ImageMarginGradientMiddle { get { return fundo; } }
            public override Color ImageMarginGradientEnd { get { return fundo; } }
            public override Color MenuBorder { get { return borda; } }
            public override Color MenuItemBorder { get { return sel; } }
            public override Color MenuItemSelected { get { return sel; } }
            public override Color MenuItemSelectedGradientBegin { get { return sel; } }
            public override Color MenuItemSelectedGradientEnd { get { return sel; } }
            public override Color SeparatorDark { get { return borda; } }
            public override Color SeparatorLight { get { return fundo; } }
        }
    }
}
