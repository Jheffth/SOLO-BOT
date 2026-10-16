using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace Bella {
    // UMA TELA EM HTML (pasta "ui") dentro de um WebView2, trancada:
    //   · só abre https://bella.local/ (a pasta ui mapeada); qualquer outro endereço é barrado;
    //   · sem janelas novas, sem menus do navegador, sem zoom, sem permissões (câmera, local…);
    //   · só aceita mensagens vindas da própria página.
    // O que chega antes da página dizer "pronto" fica numa fila e vai depois.
    sealed class Vista {
        public const string Origem="https://bella.local/";
        readonly WebView2 web;
        readonly List<string> fila=new List<string>();
        readonly JavaScriptSerializer json=new JavaScriptSerializer { MaxJsonLength=32*1024*1024 };
        bool pronto;
        public event Action<Dictionary<string,object>> Recebeu;
        public bool Pronta { get { return pronto; } }

        public Vista(WebView2 controle) { web=controle; }

        public async Task Iniciar(CoreWebView2Environment ambiente,string pastaUi,string pagina) {
            await web.EnsureCoreWebView2Async(ambiente);
            var core=web.CoreWebView2;
            core.Settings.AreDevToolsEnabled=false;
            core.Settings.AreDefaultContextMenusEnabled=false;
            core.Settings.IsStatusBarEnabled=false;
            core.Settings.IsZoomControlEnabled=false;
            core.Settings.AreBrowserAcceleratorKeysEnabled=false;
            core.Settings.IsPasswordAutosaveEnabled=false;
            core.Settings.IsGeneralAutofillEnabled=false;
            core.SetVirtualHostNameToFolderMapping("bella.local",pastaUi,CoreWebView2HostResourceAccessKind.Deny);
            core.NavigationStarting+=(s,e)=>{ if(!(e.Uri ?? "").StartsWith(Origem,StringComparison.Ordinal)) e.Cancel=true; };
            core.NewWindowRequested+=(s,e)=>{ e.Handled=true; };
            core.PermissionRequested+=(s,e)=>{ e.State=CoreWebView2PermissionState.Deny; };
            core.ProcessFailed+=(s,e)=>{ pronto=false; try { core.Reload(); } catch { } };
            core.WebMessageReceived+=(s,e)=>{
                if(!(e.Source ?? "").StartsWith(Origem,StringComparison.Ordinal)) return;
                Dictionary<string,object> d;
                try { d=json.Deserialize<Dictionary<string,object>>(e.WebMessageAsJson); } catch { return; }
                if(d==null) return;
                if(Texto(d,"acao")=="pronto") {
                    pronto=true;
                    foreach(var m in fila) core.PostWebMessageAsJson(m);
                    fila.Clear();
                }
                if(Recebeu!=null) Recebeu(d);
            };
            core.Navigate(Origem+pagina);
        }

        public void Postar(object mensagem) {
            var texto=json.Serialize(mensagem);
            if(!pronto || web.CoreWebView2==null) {
                fila.Add(texto);
                if(fila.Count>200) fila.RemoveAt(0);
                return;
            }
            try { web.CoreWebView2.PostWebMessageAsJson(texto); } catch { pronto=false; fila.Add(texto); }
        }

        // ── Leitura das mensagens da tela ─────────────────────────────
        public static string Texto(Dictionary<string,object> d,string k) {
            object v; return d.TryGetValue(k,out v) ? v as string : null;
        }
        public static bool? Logico(Dictionary<string,object> d,string k) {
            object v; if(!d.TryGetValue(k,out v) || !(v is bool)) return null; return (bool)v;
        }
        public static string[] Textos(Dictionary<string,object> d,string k) {
            object v;
            if(!d.TryGetValue(k,out v) || v is string || !(v is System.Collections.IEnumerable))
                throw new InvalidOperationException("Informe de uma a três frases de ativação.");
            var textos=new List<string>();
            foreach(var item in (System.Collections.IEnumerable)v) {
                if(!(item is string)) throw new InvalidOperationException("As frases precisam ser textos.");
                textos.Add((string)item);
            }
            return textos.ToArray();
        }
        public static int? Inteiro(Dictionary<string,object> d,string k) {
            object v; if(!d.TryGetValue(k,out v) || v==null) return null;
            try {
                if(v is int || v is long || v is decimal || v is double) return Convert.ToInt32(v);
            } catch(OverflowException) { }
            return null;
        }
    }
}
