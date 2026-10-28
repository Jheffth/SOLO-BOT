using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace Bella {
    // RECORTE DE TELA — a "Ferramenta de Captura" da Bella.
    //
    // POR QUE UMA THREAD PRÓPRIA
    // O resto do app é "DPI aware" no modo do sistema (uma escala só). Com monitores em
    // escalas diferentes (100%, 125%, 150%…), nesse modo o Windows entrega coordenadas
    // "esticadas" de alguns monitores e a captura sai deslocada ou borrada. Aqui, só esta
    // thread passa para "por monitor" (PER_MONITOR_AWARE_V2): enxerga cada monitor em pixels
    // reais. O resto da Bella não muda.
    //
    // COMO FUNCIONA
    //   1. congela todos os monitores numa imagem só (a área de trabalho virtual, em pixels reais);
    //   2. cobre cada monitor com uma camada escurecida que mostra a imagem congelada;
    //   3. arrastar recorta (pode atravessar monitores); clicar pega a janela sob o mouse;
    //      Enter = este monitor; Shift+Enter = todos; Esc ou botão direito = cancelar.
    // O recorte volta como Bitmap em pixels reais. Nada sai do computador aqui.
    public static class CapturaTela {
        [StructLayout(LayoutKind.Sequential)] internal struct RECT {
            public int Left,Top,Right,Bottom;
            public Rectangle R { get { return Rectangle.FromLTRB(Left,Top,Right,Bottom); } }
        }
        delegate bool MonitorProc(IntPtr monitor,IntPtr hdc,ref RECT area,IntPtr data);
        delegate bool JanelaProc(IntPtr hwnd,IntPtr data);
        [DllImport("user32.dll")] static extern bool EnumDisplayMonitors(IntPtr hdc,IntPtr clip,MonitorProc proc,IntPtr data);
        [DllImport("user32.dll")] static extern bool EnumWindows(JanelaProc proc,IntPtr data);
        [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
        [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
        [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
        [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h,StringBuilder s,int n);
        [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h,out RECT r);
        [DllImport("user32.dll")] static extern IntPtr SetThreadDpiAwarenessContext(IntPtr contexto);
        [DllImport("dwmapi.dll")] static extern int DwmGetWindowAttribute(IntPtr h,int atributo,out RECT valor,int tamanho);
        [DllImport("dwmapi.dll",EntryPoint="DwmGetWindowAttribute")] static extern int DwmGetWindowAttributeInt(IntPtr h,int atributo,out int valor,int tamanho);

        const int LadoEnvio=1280;           // o mesmo limite do anexo do chat (bella.js)

        /// <summary>Abre o recorte. Devolve a imagem em pixels reais, ou null se cancelado.</summary>
        public static Task<Bitmap> Recortar() {
            var pronto=new TaskCompletionSource<Bitmap>();
            var t=new Thread(()=> {
                try {
                    UsarDpiPorMonitor();
                    using(var sessao=new Sessao()) {
                        Application.Run(sessao);
                        pronto.TrySetResult(sessao.Resultado);
                    }
                } catch(Exception e) { pronto.TrySetException(e); }
            });
            t.Name="Bella recorte"; t.IsBackground=true;
            t.SetApartmentState(ApartmentState.STA);
            t.Start();
            return pronto.Task;
        }

        static void UsarDpiPorMonitor() {
            try {
                // -4 = PER_MONITOR_AWARE_V2 (Windows 10 1703+); -3 = PER_MONITOR_AWARE (1607+).
                if(SetThreadDpiAwarenessContext(new IntPtr(-4))==IntPtr.Zero) SetThreadDpiAwarenessContext(new IntPtr(-3));
            } catch(EntryPointNotFoundException) { /* Windows antigo: uma escala só, que já basta. */ }
        }

        // ── O que há na tela (chamado dentro da thread por monitor) ─────
        internal static List<Rectangle> Monitores() {
            var lista=new List<Rectangle>();
            MonitorProc proc=(IntPtr m,IntPtr dc,ref RECT area,IntPtr d)=> { lista.Add(area.R); return true; };
            EnumDisplayMonitors(IntPtr.Zero,IntPtr.Zero,proc,IntPtr.Zero);
            GC.KeepAlive(proc);
            if(lista.Count==0) lista.Add(SystemInformation.VirtualScreen);
            return lista;
        }

        /// <summary>Janelas visíveis, de cima para baixo, com a borda real (sem a sombra do Windows).</summary>
        internal static List<Rectangle> Janelas(Rectangle area) {
            var lista=new List<Rectangle>();
            uint proprio=(uint)System.Diagnostics.Process.GetCurrentProcess().Id;
            var classe=new StringBuilder(64);
            JanelaProc proc=(h,d)=> {
                try {
                    if(!IsWindowVisible(h) || IsIconic(h)) return true;
                    uint pid; GetWindowThreadProcessId(h,out pid); if(pid==proprio) return true;
                    int oculta;
                    if(DwmGetWindowAttributeInt(h,14,out oculta,4)==0 && oculta!=0) return true;   // DWMWA_CLOAKED (outra área de trabalho, app suspenso)
                    classe.Length=0; GetClassName(h,classe,classe.Capacity);
                    var nome=classe.ToString();
                    if(nome=="Progman" || nome=="WorkerW") return true;                           // a área de trabalho em si
                    RECT r;
                    if(DwmGetWindowAttribute(h,9,out r,Marshal.SizeOf(typeof(RECT)))!=0 && !GetWindowRect(h,out r)) return true;  // DWMWA_EXTENDED_FRAME_BOUNDS
                    var ret=Rectangle.Intersect(r.R,area);
                    if(ret.Width>=24 && ret.Height>=24) lista.Add(ret);
                } catch { }
                return true;
            };
            EnumWindows(proc,IntPtr.Zero);
            GC.KeepAlive(proc);
            return lista;
        }

        // ── Geometria (pura, testada no --self-test) ────────────────────
        internal static Rectangle Normalizar(Point a,Point b) {
            return Rectangle.FromLTRB(Math.Min(a.X,b.X),Math.Min(a.Y,b.Y),Math.Max(a.X,b.X),Math.Max(a.Y,b.Y));
        }
        internal static Rectangle Uniao(IEnumerable<Rectangle> retangulos) {
            Rectangle u=Rectangle.Empty; bool primeiro=true;
            foreach(var r in retangulos) { u=primeiro?r:Rectangle.Union(u,r); primeiro=false; }
            return u;
        }
        /// <summary>A primeira janela (a de cima) que contém o ponto.</summary>
        internal static Rectangle? JanelaEm(IList<Rectangle> janelas,Point p) {
            foreach(var j in janelas) if(j.Contains(p)) return j;
            return null;
        }
        /// <summary>O monitor que contém o ponto; fora de todos, o mais próximo.</summary>
        internal static Rectangle MonitorEm(IList<Rectangle> monitores,Point p) {
            Rectangle melhor=monitores[0]; long menor=long.MaxValue;
            foreach(var m in monitores) {
                if(m.Contains(p)) return m;
                long dx=Math.Max(0,Math.Max(m.Left-p.X,p.X-(m.Right-1))), dy=Math.Max(0,Math.Max(m.Top-p.Y,p.Y-(m.Bottom-1)));
                long d=dx*dx+dy*dy; if(d<menor) { menor=d; melhor=m; }
            }
            return melhor;
        }

        // ── Saídas ──────────────────────────────────────────────────────
        /// <summary>O que vai para o chat (e, se você pedir, ao Solo Bot): JPEG de até 1280 px no lado maior.</summary>
        public static string ParaEnviar(Bitmap imagem) {
            float k=Math.Min(1f,(float)LadoEnvio/Math.Max(imagem.Width,imagem.Height));
            int w=Math.Max(1,(int)Math.Round(imagem.Width*k)), h=Math.Max(1,(int)Math.Round(imagem.Height*k));
            using(var menor=new Bitmap(w,h,PixelFormat.Format24bppRgb)) {
                using(var g=Graphics.FromImage(menor)) {
                    g.InterpolationMode=InterpolationMode.HighQualityBicubic; g.PixelOffsetMode=PixelOffsetMode.HighQuality;
                    g.CompositingQuality=CompositingQuality.HighQuality;
                    g.DrawImage(imagem,new Rectangle(0,0,w,h),0,0,imagem.Width,imagem.Height,GraphicsUnit.Pixel);
                }
                var jpeg=ImageCodecInfo.GetImageEncoders().First(c=>c.FormatID==ImageFormat.Jpeg.Guid);
                using(var p=new EncoderParameters(1)) using(var buffer=new MemoryStream()) {
                    p.Param[0]=new EncoderParameter(System.Drawing.Imaging.Encoder.Quality,85L);
                    menor.Save(buffer,jpeg,p);
                    return "data:image/jpeg;base64,"+Convert.ToBase64String(buffer.ToArray());
                }
            }
        }

        public static void Salvar(Bitmap imagem,string caminho) {
            var formato=caminho.EndsWith(".jpg",StringComparison.OrdinalIgnoreCase) || caminho.EndsWith(".jpeg",StringComparison.OrdinalIgnoreCase)
                ? ImageFormat.Jpeg : ImageFormat.Png;
            imagem.Save(caminho,formato);
        }

        // ── Pedido por voz ou texto ─────────────────────────────────────
        static readonly Regex RePedido=new Regex(
            @"^(?:/recortar|/captura|"
            +@"(?:(?:fa[çc]a|faz|tire|tira|bate|bata)\s+)?(?:um|uma|o|a)?\s*(?:print|printscreen|screenshot|recorte|captura)(?:\s+d[ae]\s+tela)?|"
            +@"(?:recort(?:a|e|ar)|captur(?:a|e|ar)|print(?:a|e|ar))\s+(?:a\s+|uma\s+|minha\s+)?tela)"
            +@"\s*[.!]?$",RegexOptions.IgnoreCase|RegexOptions.CultureInvariant);
        /// <summary>"recorta a tela", "tira um print", "/recortar"… só a frase inteira, para não disparar por engano.</summary>
        public static bool Pedido(string texto) {
            var t=ComandosPastas.Pedido(texto) ?? "";
            return RePedido.IsMatch(t.Trim());
        }

        // ══════════════════════════════════════════════════════════════
        // A sessão: a foto congelada e uma camada por monitor
        // ══════════════════════════════════════════════════════════════
        sealed class Sessao : ApplicationContext {
            public readonly Bitmap Tela;
            public readonly Rectangle Virtual;
            public readonly List<Rectangle> Monitores, Janelas;
            public Bitmap Resultado;
            public bool Arrastando;
            public Point Inicio, Mouse;
            public Rectangle Selecao=Rectangle.Empty;
            public Rectangle? Destaque;
            readonly List<Camada> camadas=new List<Camada>();
            bool fechando;

            public Sessao() {
                Monitores=CapturaTela.Monitores();
                Virtual=Uniao(Monitores);
                Janelas=CapturaTela.Janelas(Virtual);
                Tela=new Bitmap(Virtual.Width,Virtual.Height,PixelFormat.Format32bppArgb);
                using(var g=Graphics.FromImage(Tela)) g.CopyFromScreen(Virtual.X,Virtual.Y,0,0,Virtual.Size,CopyPixelOperation.SourceCopy);
                Mouse=Cursor.Position;
                foreach(var m in Monitores) { var c=new Camada(this,m); camadas.Add(c); }
                foreach(var c in camadas) c.Show();
                var sob=camadas.FirstOrDefault(c=>c.Monitor.Contains(Mouse)) ?? camadas[0];
                sob.Activate();
                MoverMouse(Mouse);
            }

            public void MoverMouse(Point p) {
                var antes=Area(); var monitorAntes=MonitorEm(Monitores,Mouse);
                Mouse=p;
                if(Arrastando) { Selecao=Rectangle.Intersect(Normalizar(Inicio,p),Virtual); Destaque=null; }
                else Destaque=JanelaEm(Janelas,p);
                Redesenhar(antes,Area(),monitorAntes!=MonitorEm(Monitores,p));
            }
            public void Comecar(Point p) { Arrastando=true; Inicio=p; Selecao=new Rectangle(p,Size.Empty); Destaque=null; }
            public void Soltar(Point p) {
                if(!Arrastando) return;
                Arrastando=false;
                var r=Rectangle.Intersect(Normalizar(Inicio,p),Virtual);
                if(r.Width>=6 && r.Height>=6) { Concluir(r); return; }
                // Um clique: a janela sob o mouse; na área de trabalho, o monitor inteiro.
                var j=JanelaEm(Janelas,p);
                Concluir(j.HasValue ? j.Value : MonitorEm(Monitores,p));
            }
            public void Teclado(Keys tecla,bool shift) {
                if(tecla==Keys.Escape) Cancelar();
                else if(tecla==Keys.Enter) Concluir(shift ? Virtual : MonitorEm(Monitores,Mouse));
            }

            /// <summary>O que precisa ser redesenhado: a seleção (ou o destaque) com folga para a borda e a etiqueta.</summary>
            Rectangle Area() {
                var r=Arrastando ? Selecao : (Destaque ?? Rectangle.Empty);
                if(r.IsEmpty) return r;
                r.Inflate(260,110);          // cabe a etiqueta com o tamanho, que anda junto com o mouse
                return r;
            }
            void Redesenhar(Rectangle antes,Rectangle depois,bool trocouMonitor) {
                foreach(var c in camadas) {
                    if(trocouMonitor) { c.Invalidate(); continue; }   // a dica muda de monitor
                    foreach(var r in new[] { antes,depois }) {
                        if(r.IsEmpty) continue;
                        var local=Rectangle.Intersect(r,c.Monitor);
                        if(local.IsEmpty) continue;
                        local.Offset(-c.Monitor.X,-c.Monitor.Y);
                        c.Invalidate(local);
                    }
                }
            }

            public void Concluir(Rectangle r) {
                r=Rectangle.Intersect(r,Virtual);
                if(r.Width>=2 && r.Height>=2) {
                    Resultado=new Bitmap(r.Width,r.Height,PixelFormat.Format24bppRgb);
                    using(var g=Graphics.FromImage(Resultado)) {
                        g.CompositingMode=CompositingMode.SourceCopy;
                        g.DrawImage(Tela,new Rectangle(0,0,r.Width,r.Height),new Rectangle(r.X-Virtual.X,r.Y-Virtual.Y,r.Width,r.Height),GraphicsUnit.Pixel);
                    }
                }
                Fechar();
            }
            public void Cancelar() { Resultado=null; Fechar(); }
            void Fechar() {
                if(fechando) return; fechando=true;
                foreach(var c in camadas) { c.Saindo=true; c.Close(); }
                ExitThread();
            }
            protected override void Dispose(bool disposing) {
                if(disposing) { foreach(var c in camadas) c.Dispose(); camadas.Clear(); Tela.Dispose(); }
                base.Dispose(disposing);
            }
        }

        // Uma camada sem borda por monitor, sempre por cima, do tamanho exato do monitor.
        sealed class Camada : Form {
            [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr h,IntPtr depois,int x,int y,int w,int ht,uint flags);
            [DllImport("user32.dll")] static extern uint GetDpiForWindow(IntPtr h);
            static readonly IntPtr NoTopo=new IntPtr(-1);
            static readonly Color Violeta=Color.FromArgb(167,139,250), Ciano=Color.FromArgb(34,211,238);

            readonly Sessao s;
            readonly Rectangle monitor;
            public Rectangle Monitor { get { return monitor; } }
            readonly Bitmap escuro;          // a foto congelada deste monitor, já escurecida
            float escala=1f;
            public bool Saindo;

            public Camada(Sessao sessao,Rectangle monitor) {
                s=sessao; this.monitor=monitor;
                FormBorderStyle=FormBorderStyle.None; ShowInTaskbar=false; TopMost=true;
                StartPosition=FormStartPosition.Manual; AutoScaleMode=AutoScaleMode.None;
                Bounds=monitor; Cursor=Cursors.Cross; KeyPreview=true; BackColor=Color.Black;
                SetStyle(ControlStyles.AllPaintingInWmPaint|ControlStyles.UserPaint|ControlStyles.OptimizedDoubleBuffer|ControlStyles.Opaque,true);
                escuro=new Bitmap(monitor.Width,monitor.Height,PixelFormat.Format32bppPArgb);
                using(var g=Graphics.FromImage(escuro)) {
                    g.CompositingMode=CompositingMode.SourceCopy;
                    g.DrawImage(s.Tela,new Rectangle(0,0,monitor.Width,monitor.Height),
                        new Rectangle(monitor.X-s.Virtual.X,monitor.Y-s.Virtual.Y,monitor.Width,monitor.Height),GraphicsUnit.Pixel);
                    g.CompositingMode=CompositingMode.SourceOver;
                    using(var veu=new SolidBrush(Color.FromArgb(125,8,8,18))) g.FillRectangle(veu,0,0,monitor.Width,monitor.Height);
                }
            }
            protected override CreateParams CreateParams {
                get { var cp=base.CreateParams; cp.ExStyle|=0x00000080; return cp; }   // WS_EX_TOOLWINDOW: fora do Alt+Tab
            }
            protected override void OnHandleCreated(EventArgs e) {
                base.OnHandleCreated(e);
                try { escala=Math.Max(1f,GetDpiForWindow(Handle)/96f); } catch(EntryPointNotFoundException) { escala=1f; }
                Posicionar();
            }
            protected override void OnShown(EventArgs e) { base.OnShown(e); Posicionar(); }
            void Posicionar() { SetWindowPos(Handle,NoTopo,Monitor.X,Monitor.Y,Monitor.Width,Monitor.Height,0x0010|0x0040); }   // NOACTIVATE | SHOWWINDOW
            protected override void WndProc(ref Message m) {
                if(m.Msg==0x02E0) {                     // WM_DPICHANGED: a camada já tem o tamanho certo em pixels reais
                    escala=Math.Max(1f,(m.WParam.ToInt64()&0xFFFF)/96f);
                    Posicionar(); Invalidate(); m.Result=IntPtr.Zero; return;
                }
                base.WndProc(ref m);
            }
            protected override void OnFormClosing(FormClosingEventArgs e) {
                if(!Saindo && e.CloseReason==CloseReason.UserClosing) { e.Cancel=true; s.Cancelar(); return; }   // Alt+F4 = cancelar
                base.OnFormClosing(e);
            }
            protected override void Dispose(bool disposing) { if(disposing) escuro.Dispose(); base.Dispose(disposing); }

            Point Global(Point p) { return new Point(p.X+Monitor.X,p.Y+Monitor.Y); }
            protected override void OnMouseDown(MouseEventArgs e) {
                if(e.Button==MouseButtons.Right) { s.Cancelar(); return; }
                if(e.Button==MouseButtons.Left) { Capture=true; s.Comecar(Global(e.Location)); }
            }
            protected override void OnMouseMove(MouseEventArgs e) { s.MoverMouse(Global(e.Location)); }
            protected override void OnMouseUp(MouseEventArgs e) {
                if(e.Button!=MouseButtons.Left) return;
                Capture=false; s.Soltar(Global(e.Location));
            }
            protected override void OnKeyDown(KeyEventArgs e) { s.Teclado(e.KeyCode,e.Shift); }

            protected override void OnPaint(PaintEventArgs e) {
                var g=e.Graphics;
                g.CompositingMode=CompositingMode.SourceCopy; g.InterpolationMode=InterpolationMode.NearestNeighbor;
                g.PixelOffsetMode=PixelOffsetMode.Half;
                g.DrawImage(escuro,e.ClipRectangle,e.ClipRectangle,GraphicsUnit.Pixel);
                g.CompositingMode=CompositingMode.SourceOver;

                bool arrastando=s.Arrastando;
                var alvo=arrastando ? s.Selecao : (s.Destaque ?? Rectangle.Empty);
                var local=Rectangle.Intersect(alvo,Monitor);
                if(!local.IsEmpty) {
                    // dentro da seleção, a tela em cores, sem o véu
                    var origem=new Rectangle(local.X-s.Virtual.X,local.Y-s.Virtual.Y,local.Width,local.Height);
                    local.Offset(-Monitor.X,-Monitor.Y);
                    g.CompositingMode=CompositingMode.SourceCopy;
                    g.DrawImage(s.Tela,local,origem,GraphicsUnit.Pixel);
                    g.CompositingMode=CompositingMode.SourceOver;
                }
                g.SmoothingMode=SmoothingMode.AntiAlias; g.PixelOffsetMode=PixelOffsetMode.Default;
                g.TextRenderingHint=TextRenderingHint.ClearTypeGridFit;
                if(!alvo.IsEmpty && alvo.IntersectsWith(Monitor)) {
                    var borda=alvo; borda.Offset(-Monitor.X,-Monitor.Y);
                    using(var caneta=new Pen(arrastando?Violeta:Ciano,Math.Max(2f,2f*escala))) {
                        if(!arrastando) caneta.DashPattern=new[] { 4f,3f };
                        g.DrawRectangle(caneta,borda.X,borda.Y,Math.Max(0,borda.Width-1),Math.Max(0,borda.Height-1));
                    }
                    if(arrastando && Monitor.Contains(s.Mouse)) Etiqueta(g,alvo.Width+" × "+alvo.Height,new Point(s.Mouse.X-Monitor.X,s.Mouse.Y-Monitor.Y));
                }
                if(!arrastando && Monitor.Contains(s.Mouse)) Dica(g);
            }

            void Etiqueta(Graphics g,string texto,Point perto) {
                using(var fonte=new Font("Segoe UI",12f*escala,FontStyle.Bold,GraphicsUnit.Pixel)) {
                    var tam=g.MeasureString(texto,fonte);
                    float pad=6*escala, w=tam.Width+2*pad, h=tam.Height+pad;
                    float x=perto.X+14*escala, y=perto.Y+16*escala;
                    if(x+w>ClientSize.Width) x=perto.X-w-10*escala;
                    if(y+h>ClientSize.Height) y=perto.Y-h-10*escala;
                    using(var fundo=Pilula(new RectangleF(x,y,w,h),h/2)) using(var pincel=new SolidBrush(Color.FromArgb(235,18,19,31))) g.FillPath(pincel,fundo);
                    g.DrawString(texto,fonte,Brushes.White,x+pad,y+pad/2);
                }
            }
            void Dica(Graphics g) {
                const string texto="Arraste para recortar  ·  Clique numa janela  ·  Enter: esta tela  ·  Shift+Enter: todas  ·  Esc: cancelar";
                using(var fonte=new Font("Segoe UI",13f*escala,FontStyle.Regular,GraphicsUnit.Pixel)) {
                    var tam=g.MeasureString(texto,fonte);
                    float pad=12*escala, w=tam.Width+2*pad+18*escala, h=tam.Height+pad;
                    float x=(ClientSize.Width-w)/2, y=22*escala;
                    using(var fundo=Pilula(new RectangleF(x,y,w,h),h/2))
                    using(var pincel=new SolidBrush(Color.FromArgb(235,18,19,31)))
                    using(var borda=new Pen(Color.FromArgb(110,167,139,250),1f)) { g.FillPath(pincel,fundo); g.DrawPath(borda,fundo); }
                    float r=8*escala;
                    using(var ponto=new LinearGradientBrush(new RectangleF(x+pad,y+(h-r)/2,r,r),Violeta,Ciano,45f)) g.FillEllipse(ponto,x+pad,y+(h-r)/2,r,r);
                    using(var cor=new SolidBrush(Color.FromArgb(236,237,247))) g.DrawString(texto,fonte,cor,x+pad+18*escala,y+pad/2);
                }
            }
            static GraphicsPath Pilula(RectangleF r,float raio) {
                var p=new GraphicsPath(); float d=Math.Min(raio*2,Math.Min(r.Width,r.Height));
                p.AddArc(r.X,r.Y,d,d,180,90); p.AddArc(r.Right-d,r.Y,d,d,270,90);
                p.AddArc(r.Right-d,r.Bottom-d,d,d,0,90); p.AddArc(r.X,r.Bottom-d,d,d,90,90);
                p.CloseFigure(); return p;
            }
        }
    }
}
