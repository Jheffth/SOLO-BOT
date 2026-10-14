using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;

namespace Bella {
    public sealed class ComandoPasta {
        public string Id=Guid.NewGuid().ToString("N");
        public string Frase;
        public string Caminho;
        public string Tipo="pasta"; // Cadastros anteriores continuam sendo pastas.
        public string Termo;
    }
    public static class ComandosPastas {
        public static string Pedido(string frase) {
            string f=(frase ?? "").Trim();
            f=Regex.Replace(f,@"^(?:(?:ei|oi|olá|ola)\s+)?(?:bella|bela)\b[\s,:.!?—-]*","",RegexOptions.IgnoreCase);
            for(int i=0;i<3;i++) f=Regex.Replace(f,@"^(?:(?:eu\s+)?(?:quero|gostaria|preciso|desejo)(?:\s+que)?(?:\s+de)?\s+(?:(?:voce|você)\s+)?|(?:(?:voce|você)\s+)?(?:pode|poderia)\s+|por favor[,\s]+)","",RegexOptions.IgnoreCase).Trim();
            return Regex.Replace(f,@"[,\s]+por favor[.!?]*$","",RegexOptions.IgnoreCase).Trim();
        }
        public static string Chave(string frase) {
            string f=Arquivos.Dobrar(Pedido(frase));
            f=Regex.Replace(f,@"[^\p{L}\p{Nd}\s]"," ");
            f=Regex.Replace(f,@"\s+"," ").Trim();
            f=Regex.Replace(f,@"^(?:abra|abre|abrir|abrisse)\b","abrir");
            f=Regex.Replace(f,@"^(?:pesquisar|pesquise|pesquisa)\b","pesquisar");
            return Regex.Replace(f,@"^abrir\s+(?:o|a|os|as)\s+","abrir ");
        }
        public static string ConferirPasta(string caminho) {
            string p=Arquivos.Canonico((caminho ?? "").Trim().Trim('"'));
            Arquivos.ConferirAtalhos(p);
            if(!Directory.Exists(p)) throw new InvalidOperationException("Essa pasta não está disponível. Confira o caminho ou use Escolher pasta.");
            return p;
        }
        public static ComandoPasta[] Atualizar(IEnumerable<ComandoPasta> atuais,string id,string frase,string caminho,bool remover=false,string tipo="pasta",string termo=null) {
            var lista=(atuais ?? new ComandoPasta[0]).Select(c=>new ComandoPasta {Id=c.Id,Frase=c.Frase,Caminho=c.Caminho,Tipo=c.Tipo,Termo=c.Termo}).ToList();
            int i=String.IsNullOrEmpty(id) ? -1 : lista.FindIndex(c=>c.Id==id);
            if(!String.IsNullOrEmpty(id) && i<0) throw new InvalidOperationException("Esse comando mudou. Escolha-o novamente na lista.");
            if(remover) {
                if(i<0) throw new InvalidOperationException("Escolha o comando que deseja remover.");
                lista.RemoveAt(i); return lista.ToArray();
            }
            frase=(frase ?? "").Trim(); string chave=Chave(frase);
            if(frase.Length>200 || chave.Length<3 || frase.StartsWith("/") || Arquivos.EhResposta(frase))
                throw new InvalidOperationException("Use uma frase de 3 a 200 caracteres, como Abrir minha pasta de Projetos. Números e respostas de confirmação não podem ser comandos.");
            if(lista.Any(c=>c.Id!=id && Chave(c.Frase)==chave)) throw new InvalidOperationException("Essa frase já está cadastrada. Edite o comando existente ou escolha outra frase.");
            tipo=String.IsNullOrEmpty(tipo) ? "pasta" : tipo;
            if(tipo!="pasta" && tipo!="site" && !Navegador.Pesquisa(tipo)) throw new InvalidOperationException("Escolha um tipo de comando da lista.");
            bool variavel=frase.Contains("{assunto}");
            if(variavel && (!Navegador.Pesquisa(tipo) || frase.Split(new[] {"{assunto}"},StringSplitOptions.None).Length!=2 || frase.Replace("{assunto}","").Trim().Length<3))
                throw new InvalidOperationException("Use {assunto} uma única vez, apenas em comandos de pesquisa.");
            string alvo=tipo=="pasta" ? ConferirPasta(caminho) : tipo=="site" ? Navegador.Site(caminho) : "";
            termo=Navegador.Pesquisa(tipo) && !variavel ? Navegador.Assunto(termo) : "";
            var novo=new ComandoPasta {Id=i<0 ? Guid.NewGuid().ToString("N") : id,Frase=frase,Caminho=alvo,Tipo=tipo,Termo=termo};
            if(i<0) lista.Add(novo); else lista[i]=novo;
            if(lista.Count>50) throw new InvalidOperationException("Você pode cadastrar até 50 comandos.");
            return lista.ToArray();
        }
    }
}
