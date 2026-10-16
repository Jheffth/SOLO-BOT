using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

namespace Bella {
    public interface IEditorWord { string Executar(string texto); }
    public sealed class EditorWord : IEditorWord {
        delegate bool Enumerar(IntPtr janela,IntPtr parametro);
        [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr janela,Enumerar callback,IntPtr parametro);
        [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr janela,StringBuilder nome,int tamanho);
        [DllImport("oleacc.dll")] static extern int AccessibleObjectFromWindow(IntPtr janela,uint id,ref Guid iid,[MarshalAs(UnmanagedType.IDispatch)] out object objeto);
        static void Liberar(object o) { if(o!=null && Marshal.IsComObject(o)) Marshal.ReleaseComObject(o); }
        static object DaJanela(Process[] processos) {
            object encontrado=null;
            foreach(var processo in processos) {
                if(processo.MainWindowHandle==IntPtr.Zero) continue;
                EnumChildWindows(processo.MainWindowHandle,(janela,parametro)=> {
                    var classe=new StringBuilder(64); GetClassName(janela,classe,classe.Capacity);
                    if(classe.ToString()!="_WwG") return true;
                    object objeto=null; var iid=new Guid("00020400-0000-0000-C000-000000000046");
                    try {
                        if(AccessibleObjectFromWindow(janela,0xFFFFFFF0,ref iid,out objeto)>=0 && objeto!=null)
                            encontrado=((dynamic)objeto).Application;
                    } catch(COMException) { }
                    finally {Liberar(objeto);}
                    return encontrado==null;
                },IntPtr.Zero);
                if(encontrado!=null) break;
            }
            return encontrado;
        }
        public string Executar(string texto) {
            object aplicativo=null, documentos=null, documento=null, selecao=null, faixa=null;
            bool inseriu=false;
            try {
                try { aplicativo=Marshal.GetActiveObject("Word.Application"); }
                catch(COMException) {
                    var processos=Process.GetProcessesByName("WINWORD"); bool aberto=processos.Length>0;
                    try {if(aberto) aplicativo=DaJanela(processos);} finally {foreach(var processo in processos) processo.Dispose();}
                    if(aplicativo==null) {
                        if(aberto) throw new InvalidOperationException("O Word está aberto, mas ainda não está disponível para automação. Abra um documento e saia de qualquer janela de diálogo antes de tentar novamente.");
                        var tipo=Type.GetTypeFromProgID("Word.Application");
                        if(tipo==null) throw new InvalidOperationException("O Microsoft Word para Windows não está instalado neste computador.");
                        aplicativo=Activator.CreateInstance(tipo);
                    }
                }
                dynamic app=aplicativo;
                app.Visible=true;
                documentos=app.Documents;
                if(((dynamic)documentos).Count==0) documento=((dynamic)documentos).Add();
                else documento=app.ActiveDocument;
                string nome=((dynamic)documento).Name;
                if(texto!=null) {
                    if(String.IsNullOrWhiteSpace(texto) || texto.Length>12000 || texto.IndexOf('\0')>=0)
                        throw new InvalidOperationException("Informe um texto de até 12 mil caracteres para escrever.");
                    if(((dynamic)documento).ReadOnly || ((dynamic)documento).ProtectionType!=-1)
                        throw new InvalidOperationException("O documento está protegido ou somente para leitura. Libere a edição no Word antes de escrever.");
                    ((dynamic)documento).Activate();
                    selecao=app.Selection;
                    faixa=((dynamic)selecao).Range;
                    // Colapsar ao fim da seleção preserva qualquer texto selecionado.
                    ((dynamic)faixa).Collapse(0);
                    ((dynamic)faixa).InsertAfter(texto.Replace("\r\n","\n").Replace("\n","\r"));
                    inseriu=true;
                    try { ((dynamic)faixa).Collapse(0); ((dynamic)faixa).Select(); } catch(COMException) { }
                }
                try { app.Activate(); } catch(COMException) { }
                return (texto==null ? "Word pronto: " : "Texto inserido em: ")+nome+". O documento permanece aberto.";
            } catch(COMException) {
                if(inseriu) return "Texto inserido. Confira o documento aberto no Word.";
                throw new InvalidOperationException("O Word não concluiu a ação. Confira o documento e feche diálogos antes de repetir o pedido.");
            } finally { Liberar(faixa); Liberar(selecao); Liberar(documento); Liberar(documentos); Liberar(aplicativo); }
        }
    }
}
