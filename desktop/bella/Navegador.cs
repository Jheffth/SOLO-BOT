using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;

namespace Bella {
    public static class Navegador {
        public static bool Pesquisa(string tipo) { return tipo=="google" || tipo=="youtube" || tipo=="maps"; }
        public static string Site(string valor) {
            valor=(valor ?? "").Trim();
            if(!Regex.IsMatch(valor,@"^[a-z][a-z0-9+.-]*:",RegexOptions.IgnoreCase)) valor="https://"+valor;
            Uri uri;
            if(valor.Length>2048 || valor.Any(Char.IsControl) || !Uri.TryCreate(valor,UriKind.Absolute,out uri)
                || (uri.Scheme!="https" && uri.Scheme!="http") || String.IsNullOrEmpty(uri.Host) || !String.IsNullOrEmpty(uri.UserInfo))
                throw new InvalidOperationException("Informe um endereço HTTP ou HTTPS, sem usuário ou senha, como https://www.google.com.");
            return uri.AbsoluteUri;
        }
        public static string Assunto(string valor) {
            valor=Regex.Replace((valor ?? "").Trim(),@"\s+"," ").Trim().TrimEnd('.','!','?').Trim();
            if(valor.Length==0 || valor=="{assunto}" || valor.Length>500 || valor.Any(Char.IsControl))
                throw new InvalidOperationException("Informe o assunto da pesquisa, com até 500 caracteres.");
            return valor;
        }
        public static string Resultados(string tipo,string assunto) {
            string q=Uri.EscapeDataString(Assunto(assunto));
            string prefixo;
            switch(tipo) {
                case "google": prefixo="https://www.google.com/search?q="; break;
                case "youtube": prefixo="https://www.youtube.com/results?search_query="; break;
                case "maps": prefixo="https://www.google.com/maps/search/?api=1&query="; break;
                default: throw new InvalidOperationException("Tipo de pesquisa não reconhecido.");
            }
            if(prefixo.Length+q.Length>2048) throw new InvalidOperationException("Esse assunto gera um endereço longo demais. Use uma pesquisa mais curta.");
            return prefixo+q;
        }
        public static ComandoPasta[] Padrao() {
            return new[] {
                new ComandoPasta {Id="00000000000000000000000000000001",Tipo="google",Frase="Pesquisar no Google sobre {assunto}"},
                new ComandoPasta {Id="00000000000000000000000000000002",Tipo="youtube",Frase="Pesquisar no YouTube sobre {assunto}"},
                new ComandoPasta {Id="00000000000000000000000000000003",Tipo="maps",Frase="Pesquisar no Maps sobre {assunto}"}
            };
        }
        public static bool Casar(ComandoPasta c,string texto,out string assunto) {
            assunto=null;
            if(!Pesquisa(c.Tipo) || !(c.Frase ?? "").Contains("{assunto}")) return ComandosPastas.Chave(c.Frase)==ComandosPastas.Chave(texto);
            string[] partes=c.Frase.Split(new[] {"{assunto}"},StringSplitOptions.None);
            if(partes.Length!=2) return false;
            string prefixo=Regex.Escape(partes[0].Trim()).Replace("\\ ",@"\s+");
            string sufixo=Regex.Escape(partes[1].Trim()).Replace("\\ ",@"\s+");
            var m=Regex.Match(ComandosPastas.Pedido(texto),"^"+prefixo+(prefixo.Length>0 ? @"\s+" : "")+@"(?<assunto>.+?)"+(sufixo.Length>0 ? @"\s+"+sufixo : "")+"$",RegexOptions.IgnoreCase);
            if(!m.Success) return false;
            assunto=m.Groups["assunto"].Value; return true;
        }
        public static bool BuscaLivre(string texto,out string tipo,out string assunto) {
            tipo=null; assunto=null;
            var m=Regex.Match(ComandosPastas.Pedido(texto),@"^(pesquisar|pesquise|pesquisa|buscar|busque|procurar|procure|encontrar|encontre)\s+(.*)$",RegexOptions.IgnoreCase);
            if(!m.Success) return false;
            string resto=m.Groups[2].Value.Trim(), f=Arquivos.Dobrar(resto);
            var motor=Regex.Match(resto,@"^(?:(?:no|na|em|pelo|pela)\s+)?(?<motor>google|youtube|maps)(?:\s+|$)|\s+(?:no|na|em|pelo|pela)\s+(?<motor>google|youtube|maps)[.!?]*$",RegexOptions.IgnoreCase);
            bool explicito=motor.Success;
            if(!explicito && (!Arquivos.Dobrar(m.Groups[1].Value).StartsWith("pesquis") || Regex.IsMatch(f,@"^(?:(?:o|a|os|as|um|uma)\s+)?(?:arquivo|arquivos|pasta|pastas|diretorio)\b|[a-z]:[\\/]"))) return false;
            tipo=explicito ? motor.Groups["motor"].Value.ToLowerInvariant() : "google";
            if(explicito) resto=resto.Remove(motor.Index,motor.Length).Trim();
            assunto=Regex.Replace(resto,@"^(?:sobre|por|a respeito de)(?:\s+|$)","",RegexOptions.IgnoreCase).Trim();
            return true;
        }
        public static object[] Modelos() {
            return new object[] {
                new {Titulo="Pesquisa livre no Google",Tipo="google",Frase="Pesquisar sobre {assunto}",Caminho="",Termo=""},
                new {Titulo="Escrita criativa",Tipo="google",Frase="Pesquisar escrita criativa",Caminho="",Termo="Escrita criativa"},
                new {Titulo="Buscar vídeos",Tipo="youtube",Frase="Pesquisar vídeos sobre {assunto}",Caminho="",Termo=""},
                new {Titulo="Encontrar lugares",Tipo="maps",Frase="Encontrar no Maps {assunto}",Caminho="",Termo=""},
                new {Titulo="Abrir Gmail",Tipo="site",Frase="Abrir meu Gmail",Caminho="https://mail.google.com/",Termo=""},
                new {Titulo="Abrir agenda",Tipo="site",Frase="Abrir minha agenda",Caminho="https://calendar.google.com/",Termo=""},
                new {Titulo="WhatsApp Web",Tipo="site",Frase="Abrir WhatsApp Web",Caminho="https://web.whatsapp.com/",Termo=""},
                new {Titulo="Minha pasta de Downloads",Tipo="pasta",Frase="Abrir meus downloads",Caminho=Arquivos.PastasPadrao().FirstOrDefault(p=>p!=Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments) && p!=Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory)) ?? "",Termo=""},
                new {Titulo="Minha pasta de Documentos",Tipo="pasta",Frase="Abrir meus documentos",Caminho=Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),Termo=""}
            };
        }
    }
}
