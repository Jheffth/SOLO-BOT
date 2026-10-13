using System;
using System.IO;
using System.Text.RegularExpressions;

namespace Bella {
    // A FOTO DA BELLA — fica só neste computador, ao lado do acesso cifrado.
    //   foto.jpg            o recorte quadrado (512 px) que a tela mostra
    //   foto-original.jpg   a imagem antes do recorte, para "Recortar" de novo
    // A tela manda as duas como data URL; aqui só se confere que é imagem de verdade.
    public static class Foto {
        public static readonly string Pasta=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Solo","Bella");
        const int MaxRecorte=2*1024*1024, MaxOriginal=12*1024*1024;
        static readonly Regex DataUrl=new Regex(@"^data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)$");

        static string Arquivo(string pasta,string nome) { return Path.Combine(pasta ?? Pasta,nome); }

        public static string Recorte(string pasta=null) { return Ler(Arquivo(pasta,"foto.jpg")); }
        public static string Original(string pasta=null) { return Ler(Arquivo(pasta,"foto-original.jpg")); }

        public static void Salvar(string recorte,string original,string pasta=null) {
            var bytes=Decodificar(recorte,MaxRecorte);
            byte[] antes=null;
            if(!String.IsNullOrEmpty(original)) { try { antes=Decodificar(original,MaxOriginal); } catch { antes=null; } }
            Directory.CreateDirectory(pasta ?? Pasta);
            Gravar(Arquivo(pasta,"foto.jpg"),bytes);
            if(antes!=null) Gravar(Arquivo(pasta,"foto-original.jpg"),antes);
        }

        public static void Remover(string pasta=null) {
            foreach(var nome in new[] { "foto.jpg","foto-original.jpg" }) {
                var caminho=Arquivo(pasta,nome); if(File.Exists(caminho)) File.Delete(caminho);
            }
        }

        static string Ler(string caminho) {
            try {
                if(!File.Exists(caminho)) return null;
                var bytes=File.ReadAllBytes(caminho);
                var tipo=Tipo(bytes); if(tipo==null) return null;
                return "data:image/"+tipo+";base64,"+Convert.ToBase64String(bytes);
            } catch { return null; }
        }

        internal static byte[] Decodificar(string url,int maximo) {
            var m=DataUrl.Match(url ?? "");
            if(!m.Success) throw new InvalidOperationException("Essa imagem não pôde ser lida. Use JPG, PNG ou WEBP.");
            byte[] bytes;
            try { bytes=Convert.FromBase64String(m.Groups[2].Value); }
            catch(FormatException) { throw new InvalidOperationException("Essa imagem veio corrompida. Tente outra."); }
            if(bytes.Length==0 || bytes.Length>maximo) throw new InvalidOperationException("Essa imagem é grande demais.");
            if(Tipo(bytes)==null) throw new InvalidOperationException("Esse arquivo não é uma imagem JPG, PNG ou WEBP.");
            return bytes;
        }

        // Confere a assinatura do arquivo, não a extensão.
        internal static string Tipo(byte[] b) {
            if(b.Length>3 && b[0]==0xFF && b[1]==0xD8 && b[2]==0xFF) return "jpeg";
            if(b.Length>8 && b[0]==0x89 && b[1]==0x50 && b[2]==0x4E && b[3]==0x47) return "png";
            if(b.Length>12 && b[0]==(byte)'R' && b[1]==(byte)'I' && b[2]==(byte)'F' && b[3]==(byte)'F'
               && b[8]==(byte)'W' && b[9]==(byte)'E' && b[10]==(byte)'B' && b[11]==(byte)'P') return "webp";
            return null;
        }

        static void Gravar(string caminho,byte[] bytes) {
            var temp=caminho+"."+Guid.NewGuid().ToString("N").Substring(0,8)+".tmp";
            try {
                File.WriteAllBytes(temp,bytes);
                if(File.Exists(caminho)) File.Delete(caminho);
                File.Move(temp,caminho);
            } finally { if(File.Exists(temp)) File.Delete(temp); }
        }
    }
}
