using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;

namespace Bella {
    public sealed class ItemImagem {
        public string Id,Previa,Criada;
    }
    // Originais no disco, somente seis prévias reduzidas na interface.
    public sealed class GaleriaImagens {
        readonly string pasta;
        readonly object trava=new object();
        static readonly Regex Nome=new Regex(@"^bella-[a-f0-9]{32}\.(jpg|png)$");
        public GaleriaImagens(string directory=null) {pasta=directory ?? Path.Combine(Foto.Pasta,"imagens");}
        FileInfo[] ArquivosGerados() {
            if(!Directory.Exists(pasta)) return new FileInfo[0];
            Arquivos.ConferirAtalhos(pasta);
            return new DirectoryInfo(pasta).GetFiles().Where(f=>Nome.IsMatch(f.Name) && (f.Attributes&FileAttributes.ReparsePoint)==0)
                .OrderByDescending(f=>f.LastWriteTimeUtc).ThenBy(f=>f.Name).ToArray();
        }
        public void Guardar(Reply r) {
            lock(trava) {
                if(r.imagem_base64==null || r.imagem_base64.Length>12*1024*1024) throw new InvalidOperationException("Imagem além do limite de tamanho.");
                byte[] bytes=Convert.FromBase64String(r.imagem_base64);
                if(bytes.Length==0 || bytes.Length>8*1024*1024) throw new InvalidOperationException("Imagem além do limite de tamanho.");
                string tipo=Foto.Tipo(bytes);
                if((tipo!="jpeg" && tipo!="png") || r.imagem_mime!="image/"+tipo) throw new InvalidOperationException("Formato de imagem inválido.");
                using(var stream=new MemoryStream(bytes)) using(var img=Image.FromStream(stream,true,true)) {
                    if(img.Width>8192 || img.Height>8192 || (long)img.Width*img.Height>32000000) throw new InvalidOperationException("Dimensões de imagem além do limite.");
                }
                Directory.CreateDirectory(pasta); Arquivos.ConferirAtalhos(pasta);
                string nome="bella-"+Guid.NewGuid().ToString("N")+(tipo=="png" ? ".png" : ".jpg");
                using(var arquivo=new FileStream(Path.Combine(pasta,nome),FileMode.CreateNew,FileAccess.Write)) arquivo.Write(bytes,0,bytes.Length);
                foreach(var antigo in ArquivosGerados().Skip(6)) antigo.Delete();
            }
        }
        public ItemImagem[] Listar() {
            lock(trava) {
                return ArquivosGerados().Take(6).Select(f=> {
                    try {
                        using(var img=Image.FromFile(f.FullName)) {
                            if(img.Width>8192 || img.Height>8192 || (long)img.Width*img.Height>32000000) return null;
                            double escala=Math.Min(1.0,900.0/Math.Max(img.Width,img.Height));
                            using(var mini=new Bitmap(Math.Max(1,(int)(img.Width*escala)),Math.Max(1,(int)(img.Height*escala)))) {
                                using(var g=Graphics.FromImage(mini)) {g.Clear(Color.Black); g.InterpolationMode=InterpolationMode.HighQualityBicubic; g.DrawImage(img,0,0,mini.Width,mini.Height);}
                                using(var buffer=new MemoryStream()) {
                                    mini.Save(buffer,ImageFormat.Jpeg);
                                    return new ItemImagem {Id=f.Name,Criada=f.LastWriteTime.ToString("dd/MM/yyyy HH:mm"),Previa="data:image/jpeg;base64,"+Convert.ToBase64String(buffer.ToArray())};
                                }
                            }
                        }
                    } catch(ArgumentException) {return null;} catch(IOException) {return null;}
                }).Where(i=>i!=null).ToArray();
            }
        }
        public string Caminho(string id) {
            lock(trava) {
                if(id==null || !Nome.IsMatch(id)) throw new InvalidOperationException("Imagem não encontrada na galeria.");
                var item=ArquivosGerados().FirstOrDefault(f=>f.Name==id);
                if(item==null) throw new InvalidOperationException("Esta imagem não está mais na galeria.");
                return item.FullName;
            }
        }
    }
}
