using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace Bella {
    public static class Chamadas {
        public static string[] Padrao() { return new[] { "Olá Bella", "Oi Bella", "E aí Bella" }; }
        public static string Fonetica(string texto) {
            var s=Regex.Replace((texto ?? "").ToLowerInvariant(),@"[^\p{L}\s]"," ");
            return Regex.Replace(Regex.Replace(s,@"\bbella\b","bela"),@"\s+"," ").Trim();
        }
        public static string Normalizar(string texto) {
            var s=new StringBuilder();
            foreach(char c in Fonetica(texto).Normalize(NormalizationForm.FormD))
                if(CharUnicodeInfo.GetUnicodeCategory(c)!=UnicodeCategory.NonSpacingMark) s.Append(c);
            return s.ToString().Normalize(NormalizationForm.FormC);
        }
        public static string[] Validar(string[] frases) {
            if(frases==null || frases.Length>3) throw new InvalidOperationException("Cadastre de uma a três frases de ativação.");
            var lista=new List<string>(); var usadas=new HashSet<string>();
            foreach(var frase in frases) {
                if(String.IsNullOrWhiteSpace(frase)) continue;
                var limpa=Regex.Replace(frase.Trim(),@"\s+"," ");
                var n=Normalizar(limpa);
                if(limpa.Length>80 || n.Length==0 || n.Split(' ').Length>8 || Regex.IsMatch(limpa,@"[^\p{L}\s,.!?;:—-]"))
                    throw new InvalidOperationException("Use frases de até oito palavras e 80 caracteres, somente com letras e pontuação.");
                if(!usadas.Add(n)) throw new InvalidOperationException("As frases de ativação precisam ser diferentes.");
                lista.Add(limpa);
            }
            if(lista.Count==0) throw new InvalidOperationException("Informe pelo menos uma frase de ativação.");
            return lista.ToArray();
        }
        // Só a fala final inteira, com confiança em cada palavra, pode chamar a Bella.
        public static bool Aceita(Dictionary<string,object> resultado,string[] frases) {
            object texto, itens;
            if(!resultado.TryGetValue("text",out texto) || !(texto is string) ||
               !resultado.TryGetValue("result",out itens) || !(itens is IEnumerable)) return false;
            string normal=Normalizar((string)texto);
            bool igual=false;
            foreach(var frase in frases) if(normal==Normalizar(frase)) igual=true;
            if(!igual) return false;
            var palavras=new List<string>();
            foreach(var item in (IEnumerable)itens) {
                var palavra=item as Dictionary<string,object>; object nome, confianca;
                if(palavra==null || !palavra.TryGetValue("word",out nome) || !(nome is string) ||
                   !palavra.TryGetValue("conf",out confianca) || !(confianca is double || confianca is decimal || confianca is int)) return false;
                double valor=Convert.ToDouble(confianca,CultureInfo.InvariantCulture);
                if(Double.IsNaN(valor) || valor<0.85 || valor>1) return false;
                palavras.Add((string)nome);
            }
            return palavras.Count>0 && Normalizar(String.Join(" ",palavras))==normal;
        }
    }
}
