using System;
using System.Drawing;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace Bella {
    // A MINI-BELLA: uma pílula acima da barra de tarefas, sempre por cima, que
    // aparece quando a janela está fechada e a Bella entra em ação. Não rouba o
    // foco de quem está digitando. Um clique abre a janela.
    sealed class MiniBella : Form {
        readonly WebView2 web=new WebView2();
        readonly Vista tela;
        readonly CoreWebView2Environment ambiente;
        readonly string pastaUi;
        Task iniciando;
        public event Action Abrir;
        public event Action Pronta;

        public MiniBella(CoreWebView2Environment amb,string ui) {
            ambiente=amb; pastaUi=ui;
            FormBorderStyle=FormBorderStyle.None; ShowInTaskbar=false; TopMost=true;
            StartPosition=FormStartPosition.Manual; BackColor=Visual.Fundo;
            AutoScaleMode=AutoScaleMode.None; Size=Visual.Medida(380,84);
            web.Dock=DockStyle.Fill; web.DefaultBackgroundColor=Color.FromArgb(23,24,49); Controls.Add(web);
            tela=new Vista(web);
            tela.Recebeu+=d=>{
                var acao=Vista.Texto(d,"acao");
                if(acao=="pronto" && Pronta!=null) Pronta();
                if(acao=="abrir" && Abrir!=null) Abrir();
            };
        }

        protected override bool ShowWithoutActivation { get { return true; } }
        protected override CreateParams CreateParams {
            get {
                var cp=base.CreateParams;
                cp.ExStyle|=0x08000000 | 0x00000080;     // WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW (fora do Alt+Tab)
                return cp;
            }
        }
        protected override void OnHandleCreated(EventArgs e) { base.OnHandleCreated(e); Visual.CantosRedondos(this); }

        public void Postar(object mensagem) { tela.Postar(mensagem); }

        public void Mostrar() {
            var area=Screen.PrimaryScreen.WorkingArea;
            Location=new Point(area.Left+(area.Width-Width)/2,area.Bottom-Height-(int)(18*Visual.Escala()));
            if(!Visible) Show();
            if(iniciando==null) iniciando=Iniciar();
        }
        async Task Iniciar() {
            try { await tela.Iniciar(ambiente,pastaUi,"index.html?mini=1"); }
            catch { iniciando=null; Hide(); }
        }
    }
}
