using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.VisualBasic.FileIO;

namespace Bella {
    // Somente ações locais e explícitas. Nada recebido do hub vira ação do Windows.
    public sealed class Arquivos {
        readonly Func<IEnumerable<string>> pastas;
        readonly Func<IEnumerable<ComandoPasta>> comandos;
        readonly Action<string> abrir, reciclar;
        readonly Func<DateTime> agora;
        Dictionary<int,Func<Reply>> escolhas;
        string identidade;
        DateTime validade;
        bool confirmacao;
        string assuntoPendente;
        public Arquivos(Func<IEnumerable<string>> roots,Action<string> open=null,Action<string> recycle=null,Func<DateTime> clock=null,Func<IEnumerable<ComandoPasta>> commands=null) {
            pastas=roots; abrir=open ?? Abrir; reciclar=recycle ?? Reciclar; agora=clock ?? (()=>DateTime.UtcNow);
            comandos=commands ?? (()=>new ComandoPasta[0]);
        }
        public void Cancelar() { escolhas=null; identidade=null; confirmacao=false; assuntoPendente=null; }
        public bool TemEscolha { get { return escolhas!=null || assuntoPendente!=null; } }
        public ComandoPasta[] CatalogoComandos { get {
            var salvos=(comandos() ?? new ComandoPasta[0]).Where(c=>!Programas.Tipo(c.Tipo)).ToArray();
            return salvos.Concat(Navegador.Padrao().Where(c=>!salvos.Any(s=>ComandosPastas.Chave(s.Frase)==ComandosPastas.Chave(c.Frase)))).ToArray();
        } }
        public bool PedidoLocal(string text) {
            string f=Dobrar(text);
            if((text ?? "").Trim().StartsWith("/") || EhResposta(text)) return false;
            if(Regex.IsMatch(f,@"\b(google|youtube|maps|site|navegador|internet|web)\b") && Regex.IsMatch(f,@"\b(abrir|abra|abre|acessar|acesse|ver|mostrar|mostre|buscar|busque|pesquisar|pesquise|pesquisa|procure|encontre)\b")) return true;
            if(Regex.IsMatch(f,@"\b(missao|rotina|meta|tarefa|banco|conta|saldo|extrato|recebi|gastei|paguei|transferir)\b")) return false;
            if(!Regex.IsMatch(f,@"\b(abrir|abra|abre|abrisse|acessar|acesse|acessa|mostrar|mostre|ver|visualizar|leve|levar|ir|entrar|trabalhar|programar|pesquisar|pesquise|buscar|busque|encontre)\b")) return false;
            return Regex.IsMatch(f,@"\b(pasta|pastas|diretorio|diretorios|downloads|documentos|desktop|area de trabalho)\b")
                || CatalogoComandos.Any(c=>Regex.Split(ComandosPastas.Chave(c.Frase),@"\s+").Any(t=>t.Length>=3
                    && !Regex.IsMatch(t,@"^(abrir|minha|minhas|meu|meus|pasta|pastas|para|por|favor|hora|quero)$")
                    && Regex.IsMatch(f,@"\b"+Regex.Escape(t)+@"\b")));
        }
        public bool PodeInterpretar(string text) {
            return CatalogoComandos.Length>0 && PedidoLocal(text)
                && !Regex.IsMatch(Dobrar(Limpar(text)),@"^(?:nao|nunca)\b")
                && !Regex.IsMatch(Dobrar(text),@"\b(excluir|exclua|apagar|apague|deletar|delete|mover|mova|renomear|renomeie|criar|crie)\b")
                && !Regex.IsMatch(text ?? "",@"[a-zA-Z]:[\\/]");
        }
        public Task<Reply> Processar(string text) { return Executar(()=>Atender(text)); }
        public Task<Reply> Interpretar(InterpretacaoComando resultado,string pedido=null) {
            return Executar(()=> {
                Cancelar(); var catalogo=CatalogoComandos;
                var ids=resultado==null ? new string[0] : resultado.candidatos ?? new string[0];
                var escolhido=ids.Length>1 ? null : catalogo.SingleOrDefault(c=>c.Id==(resultado==null ? null : resultado.comando_id));
                if(escolhido!=null) return AcaoComando(escolhido.Id,resultado.assunto);
                var candidatos=catalogo.Where(c=>ids.Contains(c.Id)).ToArray();
                if(candidatos.Length==0) candidatos=catalogo;
                if(ids.Length==0 && Regex.IsMatch(Dobrar(pedido),@"\b(pasta|pastas|diretorio|diretorios)\b")) candidatos=candidatos.Where(c=>(c.Tipo ?? "pasta")=="pasta").ToArray();
                if(candidatos.Length==0) return Resposta("erro","Cadastre uma ação na aba Comandos para eu executar diretamente.");
                return Oferecer(candidatos.Take(10).Select(c=>new KeyValuePair<string,Func<Reply>>(c.Frase,()=>AcaoComando(c.Id,resultado==null ? null : resultado.assunto))).ToList(),
                    "escolha","Qual destes comandos você quer usar?"+(candidatos.Length>10 ? " Mostrando os 10 primeiros comandos; diga a frase cadastrada para escolher outro." : ""),false);
            });
        }
        Task<Reply> Executar(Func<Reply> acao) {
            // Explorer e Lixeira usam o Shell do Windows, que exige uma thread STA.
            // A busca não bloqueia a janela e o provedor nativo roda no mesmo contexto.
            var resultado=new TaskCompletionSource<Reply>();
            var thread=new Thread(()=> {
                try { resultado.SetResult(acao()); }
                catch(Exception e) { resultado.SetException(e); }
            });
            thread.IsBackground=true; thread.Name="BellaArquivos";
            thread.SetApartmentState(ApartmentState.STA); thread.Start(); return resultado.Task;
        }
        public static string Dobrar(string value) {
            var b=new StringBuilder();
            foreach(char c in (value ?? "").Normalize(NormalizationForm.FormD))
                if(CharUnicodeInfo.GetUnicodeCategory(c)!=UnicodeCategory.NonSpacingMark) b.Append(Char.ToLowerInvariant(c));
            return b.ToString().Normalize(NormalizationForm.FormC);
        }
        static string Limpar(string text) {
            return ComandosPastas.Pedido(text);
        }
        static string Nome(string text,bool preservarAspas=false) {
            text=Regex.Replace((text ?? "").Trim(),@"^(?:(?:o|a|os|as|um|uma)\s+)?(?:nov[oa]\s+)?(?:arquivo(?:s)?|pasta(?:s)?|diretório|diretorio)\s+","",RegexOptions.IgnoreCase);
            text=Regex.Replace(text,@"^(?:nova\s+|novo\s+)?(?:chamad[ao]\s+)?","",RegexOptions.IgnoreCase);
            text=text.Trim().TrimEnd('.','!','?').Trim();
            return preservarAspas ? text : text.Trim('"','“','”','\'');
        }
        static string Referencia(string text) {
            // Possessivos descrevem o acesso, não fazem parte do nome procurado.
            // Aspas preservam nomes literais; criação e renomeação continuam usando Nome.
            text=(text ?? "").Trim();
            if(text.StartsWith("\"") || text.StartsWith("“") || text.StartsWith("'")) return text;
            text=Regex.Replace(text,@"^(?:(?:o|a|os|as)\s+)?(?:meu|minha|meus|minhas)\s+","",RegexOptions.IgnoreCase);
            text=Regex.Replace(text,@"^(?:(?:o|a|os|as|um|uma)\s+)?(?:arquivo(?:s)?|pasta(?:s)?|diretório|diretorio)\s+(?:de|do|da|dos|das)\s+","",RegexOptions.IgnoreCase);
            return Nome(text,true);
        }
        static Reply Resposta(string codigo,string texto,string falar=null,Opcao[] opcoes=null) {
            string curto;
            switch(codigo) {
                case "ajuda": curto="Posso buscar, listar e abrir arquivos, e criar pastas. Para mover, renomear ou excluir, peço sua confirmação."; break;
                case "listagem": case "busca": curto="Aqui estão os resultados. Para abrir um item, diga o número."; break;
                case "escolha": curto="Qual destas opções você quer? Diga o número."; break;
                case "confirmar_mover": curto="Confira o item e a pasta de destino na tela. Posso mover?"; break;
                case "confirmar_renomear": curto="Confira o item e o novo nome na tela. Posso renomear?"; break;
                case "confirmar_excluir": curto="Confira o item que irá para a Lixeira. Posso excluir?"; break;
                case "criada": curto="Criei a pasta."; break;
                case "existe": curto="Esse item já existe."; break;
                case "aberto": curto="Abri o item."; break;
                case "site_aberto": curto="Abri o site no seu navegador padrão."; break;
                case "pesquisa_aberta": curto="Abri os resultados da pesquisa no seu navegador padrão."; break;
                case "pedir_assunto": curto="Qual assunto você quer pesquisar?"; break;
                case "movido": curto="Pronto, movi o item."; break;
                case "renomeado": curto="Pronto, renomeei o item."; break;
                case "excluido": curto="Concluí a exclusão pelo Windows."; break;
                case "cancelado": curto="Pedido cancelado."; break;
                case "vazio": curto="Não encontrei itens nas pastas consultadas."; break;
                case "expirou": curto="Essa escolha expirou. Faça o pedido de arquivo novamente."; break;
                default: curto="Não consegui concluir esse comando. Confira a mensagem na tela."; break;
            }
            string selo=codigo=="site_aberto" || codigo=="pesquisa_aberta" || codigo=="pedir_assunto" ? "🌐 Navegador" : "📁 Arquivos";
            return new Reply { CodigoVoz=codigo, texto=selo+"\n"+texto, falar=falar ?? curto, opcoes=opcoes };
        }
        Reply AcaoComando(string id,string assunto=null) {
            try {
                var c=CatalogoComandos.SingleOrDefault(x=>x.Id==id);
                if(c==null) return Resposta("expirou","Esse comando não está mais disponível. Confira a aba Comandos.");
                string tipo=c.Tipo ?? "pasta";
                if(tipo=="pasta") { string p=ComandosPastas.ConferirPasta(c.Caminho); abrir(p); return Resposta("aberto","Abri:\n"+p); }
                if(tipo=="site") { string url=Navegador.Site(c.Caminho); abrir(url); return Resposta("site_aberto","Abri no navegador padrão:\n"+url); }
                if(!Navegador.Pesquisa(tipo)) return Resposta("erro","Esse tipo de comando não é reconhecido.");
                assunto=(c.Frase ?? "").Contains("{assunto}") ? assunto : c.Termo;
                if(String.IsNullOrWhiteSpace(assunto) || assunto=="{assunto}") {
                    assuntoPendente=id; validade=agora().AddMinutes(5); return Resposta("pedir_assunto","Qual assunto você quer pesquisar? Diga ou escreva o assunto, ou “cancelar”.");
                }
                assunto=Navegador.Assunto(assunto); string destino=Navegador.Resultados(tipo,assunto); abrir(destino);
                return Resposta("pesquisa_aberta","Pesquisa: "+assunto+"\nAbri os resultados no navegador padrão:\n"+destino);
            } catch(InvalidOperationException e) { return Resposta("erro",e.Message); }
            catch(System.ComponentModel.Win32Exception) { return Resposta("erro","O Windows não conseguiu abrir esse destino. Confira o navegador padrão e o cadastro do comando."); }
            catch(UnauthorizedAccessException) { return Resposta("erro","O Windows não permitiu abrir esse destino."); }
            catch(IOException) { return Resposta("erro","Esse destino está indisponível. Confira o cadastro."); }
        }
        static int Numero(string text) {
            text=Regex.Replace(Dobrar(text).Trim().TrimEnd('.','!','?'),@"^(?:opcao|numero)\s+","");
            string[] ditos={"um","dois","tres","quatro","cinco","seis","sete","oito","nove","dez"};
            int n; if(Int32.TryParse(text,out n)) return n;
            return Array.IndexOf(ditos,text)+1;
        }
        public static bool EhResposta(string text) {
            string f=Dobrar(Limpar(text)).TrimEnd('.','!','?');
            return Numero(f)>0 || f=="sim" || f=="confirmar" || f=="confirmo" || f=="nao" || f=="cancelar";
        }
        public Reply Atender(string text) {
            text=Limpar(text); string f=Dobrar(text).TrimEnd('.','!','?');
            var botao=Regex.Match(text,@"^/arquivos escolher ([a-f0-9]{32}) (\d+)$");
            bool resposta=EhResposta(text);
            try {
                if(assuntoPendente!=null) {
                    string id=assuntoPendente; Cancelar();
                    if(agora()>validade) return Resposta("expirou","Essa pesquisa expirou. Faça o pedido novamente.");
                    if(f=="nao" || f=="cancelar") return Resposta("cancelado","Pesquisa cancelada.");
                    if(!text.StartsWith("/")) return AcaoComando(id,text);
                }
                if(botao.Success || (escolhas!=null && resposta)) {
                    if(escolhas==null || agora()>validade || (botao.Success && botao.Groups[1].Value!=identidade)) {
                        Cancelar(); return Resposta("expirou","Essa escolha de arquivo expirou. Faça o pedido novamente.");
                    }
                    int n=botao.Success ? Int32.Parse(botao.Groups[2].Value) : Numero(f);
                    if(confirmacao && (f=="sim" || f=="confirmar" || f=="confirmo")) n=1;
                    if(f=="nao" || f=="cancelar") { Cancelar(); return Resposta("cancelado","Pedido de arquivo cancelado."); }
                    Func<Reply> acao;
                    if(!escolhas.TryGetValue(n,out acao)) return Resposta("erro","Diga um dos números da lista ou “cancelar”.");
                    Cancelar(); return acao(); // A escolha é consumida antes de mexer no arquivo.
                }
                var porId=Regex.Match(text,@"^/arquivos comando ([a-f0-9]{32})$");
                if(porId.Success) {
                    Cancelar(); return AcaoComando(porId.Groups[1].Value);
                }
                if(PedidoLocal(text) && Regex.IsMatch(Dobrar(text),@"^(?:nao|nunca)\b")) { Cancelar(); return Resposta("cancelado","Pedido cancelado."); }
                string assuntoBusca=null;
                var cadastrados=CatalogoComandos.Where(c=> {string s; bool casa=Navegador.Casar(c,text,out s); if(casa) assuntoBusca=s; return casa;}).ToList();
                if(cadastrados.Count>0) {
                    Cancelar();
                    if(cadastrados.Count!=1) return Resposta("erro","Há mais de um comando com essa frase. Corrija os cadastros na aba Comandos.");
                    return AcaoComando(cadastrados[0].Id,assuntoBusca);
                }
                string tipoBusca;
                if(Navegador.BuscaLivre(text,out tipoBusca,out assuntoBusca)) {
                    Cancelar(); var padrao=Navegador.Padrao().Single(c=>c.Tipo==tipoBusca);
                    var destino=CatalogoComandos.First(c=>c.Id==padrao.Id || ComandosPastas.Chave(c.Frase)==ComandosPastas.Chave(padrao.Frase));
                    return AcaoComando(destino.Id,assuntoBusca);
                }
                bool explicito=Regex.IsMatch(f,@"^/?arquivos\b");
                if(explicito) text=Regex.Replace(text,@"^/?arquivos\s*","",RegexOptions.IgnoreCase);
                var comando=Regex.Match(text,@"^(listar|liste|lista|buscar|busque|pesquisar|pesquise|pesquisa|procurar|procure|encontrar|encontre|abrir|abra|abre|criar|crie|cria|mover|mova|move|renomear|renomeie|excluir|exclua|apagar|apague)\b\s*(.*)$",RegexOptions.IgnoreCase);
                if(!explicito && (!comando.Success || !PareceArquivo(comando.Groups[2].Value))) return null;
                Cancelar();
                if(!comando.Success) return Ajuda();
                string verbo=Dobrar(comando.Groups[1].Value), resto=comando.Groups[2].Value.Trim();
                if(verbo.StartsWith("list")) {
                    string p=Pasta(resto); bool parcial=false;
                    var itens=Ler(new[] { p },false,ref parcial);
                    return Resultados(itens,"listagem","Itens de "+p,parcial);
                }
                if(verbo.StartsWith("busc") || verbo.StartsWith("pesquis") || verbo.StartsWith("procur") || verbo.StartsWith("encontr")) {
                    string termo, lugar; SepararLugar(Referencia(resto),out termo,out lugar);
                    string[] roots=lugar==null ? Raizes() : new[] { Pasta(lugar) };
                    termo=Dobrar(Nome(Referencia(termo)));
                    if(termo.Length==0) return Ajuda();
                    bool parcial=false;
                    var itens=Ler(roots,true,ref parcial).Where(p=>Dobrar(Path.GetFileName(p)).Contains(termo)).ToList();
                    return Resultados(itens,"busca","Resultados para “"+Nome(resto)+"”",parcial);
                }
                if(verbo.StartsWith("cri")) {
                    if(!Regex.IsMatch(resto,@"\bpasta\b",RegexOptions.IgnoreCase)) return Ajuda();
                    string nome, lugar; SepararLugar(Nome(resto),out nome,out lugar);
                    if(lugar==null) return Resposta("erro","Diga onde criar: “criar pasta Estudos em documentos”.");
                    string destino=Validar(Path.Combine(Pasta(lugar),NomeSeguro(Nome(nome))));
                    if(Directory.Exists(destino)) return Resposta("existe","A pasta já existe:\n"+destino);
                    if(File.Exists(destino)) throw new InvalidOperationException("Já existe um arquivo com esse nome. Escolha outro nome.");
                    Directory.CreateDirectory(destino); return Resposta("criada","Criei a pasta:\n"+destino);
                }
                if(verbo.StartsWith("abr")) return Selecionar(Resolver(resto),p=>AbrirItem(p));
                bool renomear=verbo.StartsWith("renom"), mover=verbo.StartsWith("mov");
                string origem=resto, destinoNome=null;
                if(renomear || mover) {
                    int i=Separador(resto,@"\s+para\s+");
                    if(i<0) return Resposta("erro","Diga o destino: “mover arquivo relatório.pdf para documentos” ou “renomear arquivo relatório.pdf para relatório-final.pdf”.");
                    var m=Regex.Match(resto.Substring(i),@"^\s+para\s+",RegexOptions.IgnoreCase);
                    origem=resto.Substring(0,i); destinoNome=resto.Substring(i+m.Length);
                }
                string novo=destinoNome;
                return Selecionar(Resolver(origem),p=>Preparar(p,novo,renomear ? "renomear" : mover ? "mover" : "excluir"));
            } catch(OperationCanceledException) { Cancelar(); return Resposta("cancelado","Operação cancelada."); }
            catch(UnauthorizedAccessException) { Cancelar(); return Resposta("erro","O Windows não permitiu acessar esse item. Escolha outra pasta ou confira suas permissões."); }
            catch(IOException) { Cancelar(); return Resposta("erro","Não consegui concluir: o item pode estar em uso, ter mudado ou estar indisponível. Confira o arquivo antes de repetir."); }
            catch(ArgumentException) { Cancelar(); return Resposta("erro","Esse nome ou caminho não é válido. Use o caminho completo ou um nome da lista."); }
            catch(InvalidOperationException e) { Cancelar(); return Resposta("erro",e.Message); }
        }
        bool PareceArquivo(string text) {
            string f=Dobrar(text);
            if(Regex.IsMatch(f,@"^(?:(?:o|a|uma|um)\s+)?(?:nova?\s+)?(?:missao|rotina|meta|banco|conta|tarefa)\b")) return false;
            return Regex.IsMatch(f,@"\b(arquivo|arquivos|pasta|pastas|diretorio|downloads|documentos|desktop|area de trabalho)\b|[a-z]:[\\/]|\.[a-z0-9]{1,8}\b")
                || Raizes().Any(p=>Dobrar(Path.GetFileName(p))==Nome(Referencia(f)));
        }
        public static Reply Ajuda() {
            return Resposta("ajuda","Posso cuidar dos arquivos nas pastas escolhidas em Configurações → Arquivos.\n\n"
                +"• listar downloads\n• buscar arquivo relatório em documentos\n• abrir pasta documentos\n• criar pasta Estudos em documentos\n"
                +"• mover arquivo relatório.pdf dos downloads para documentos\n• renomear arquivo relatório.pdf para relatório-final.pdf\n• excluir arquivo rascunho.txt\n\n"
                +"Mover, renomear e excluir pedem confirmação. Excluir envia à Lixeira. Para caminhos com palavras como “para”, use aspas.");
        }
        Reply Resultados(List<string> itens,string codigo,string titulo,bool parcial) {
            itens=itens.OrderBy(p=>p,StringComparer.OrdinalIgnoreCase).Distinct(StringComparer.OrdinalIgnoreCase).ToList();
            if(itens.Count==0) return Resposta("vazio",parcial ? "Não encontrei nos itens que consegui consultar. A busca foi parcial; escolha uma pasta mais específica." : "Não encontrei itens nas pastas consultadas.");
            var limitados=itens.Take(10).ToList();
            string texto=titulo+"\n"+String.Join("\n",limitados.Select((p,i)=>(i+1)+". "+p));
            if(itens.Count>10) texto+="\nMostrando os 10 primeiros. Refine a busca para encontrar os outros.";
            if(parcial) texto+="\nBusca parcial: refine a pasta para consultar os demais itens.";
            return Oferecer(limitados.Select(p=>new KeyValuePair<string,Func<Reply>>(p,()=>AbrirItem(p))).ToList(),codigo,texto,false);
        }
        Reply Selecionar(List<string> alvos,Func<string,Reply> continuar) {
            if(alvos.Count==0) return Resposta("vazio","Não encontrei esse item. Use “buscar arquivo nome” ou informe o caminho completo dentro de uma pasta escolhida.");
            if(alvos.Count==1) return continuar(alvos[0]);
            if(alvos.Count>10) return Resposta("erro","Há muitos itens com esse nome. Informe também a pasta ou o caminho completo.");
            return Oferecer(alvos.Select(p=>new KeyValuePair<string,Func<Reply>>(p,()=>continuar(p))).ToList(),"escolha","Encontrei mais de um item. Qual deles?",false);
        }
        Reply Oferecer(List<KeyValuePair<string,Func<Reply>>> acoes,string codigo,string texto,bool confirmar) {
            identidade=Guid.NewGuid().ToString("N"); validade=agora().AddMinutes(5); confirmacao=confirmar;
            escolhas=new Dictionary<int,Func<Reply>>(); var opcoes=new List<Opcao>();
            for(int i=0;i<acoes.Count;i++) {
                escolhas[i+1]=acoes[i].Value;
                opcoes.Add(new Opcao { numero=i+1, rotulo=acoes[i].Key, titulo="", comando="/arquivos escolher "+identidade+" "+(i+1) });
            }
            return Resposta(codigo,texto+"\nDiga o número"+(confirmar ? ", “sim”" : "")+" ou “cancelar”.",null,opcoes.ToArray());
        }
        Reply AbrirItem(string path) {
            path=Validar(path);
            if(!Directory.Exists(path) && !File.Exists(path)) throw new IOException();
            if(!Directory.Exists(path) && !TiposAbriveis.Contains(Path.GetExtension(path).ToLowerInvariant()))
                throw new InvalidOperationException("Este tipo de arquivo não abre pela Bella. Posso abrir a pasta para você escolher como usá-lo.");
            abrir(path); return Resposta("aberto","Abri:\n"+path);
        }
        Reply Preparar(string origem,string novo,string operacao) {
            origem=Validar(origem); if(Raizes().Any(r=>Igual(r,origem))) throw new InvalidOperationException("Escolha um item dentro dessa pasta. A pasta de acesso principal não é movida, renomeada ou excluída.");
            string destino=null;
            if(operacao=="renomear") destino=Validar(Path.Combine(Path.GetDirectoryName(origem),NomeSeguro(Nome(novo))));
            if(operacao=="mover") destino=Validar(Path.Combine(Pasta(novo),Path.GetFileName(origem)));
            if(destino!=null) {
                if(Igual(destino,origem)) return Resposta("existe","O item já tem esse nome e está nessa pasta.");
                if(File.Exists(destino) || Directory.Exists(destino)) throw new InvalidOperationException("Já existe um item no destino. Escolha outro nome ou pasta; não substituo arquivos.");
                if(Dentro(destino,origem)) throw new InvalidOperationException("Não posso mover uma pasta para dentro dela mesma.");
            }
            string assinatura=Assinatura(origem);
            string mostrar=operacao=="excluir" ? "Enviar à Lixeira:\n"+origem : (operacao=="mover" ? "Mover:" : "Renomear:")+"\n"+origem+"\nPara:\n"+destino;
            return Oferecer(new List<KeyValuePair<string,Func<Reply>>> {
                new KeyValuePair<string,Func<Reply>>("Confirmar "+(operacao=="excluir" ? "exclusão" : operacao),()=> {
                    Validar(origem);
                    if(Assinatura(origem)!=assinatura) throw new InvalidOperationException("O item mudou desde a confirmação. Faça o pedido novamente para conferir a versão atual.");
                    if(operacao=="excluir") { reciclar(origem); return Resposta("excluido","Concluí a exclusão pelo Windows:\n"+origem); }
                    Validar(destino);
                    if(File.Exists(destino) || Directory.Exists(destino)) throw new InvalidOperationException("Já existe um item no destino. Nada foi substituído.");
                    if(Directory.Exists(origem)) Directory.Move(origem,destino); else File.Move(origem,destino);
                    return Resposta(operacao=="mover" ? "movido" : "renomeado","Pronto:\n"+destino);
                }),
                new KeyValuePair<string,Func<Reply>>("Cancelar",()=>Resposta("cancelado","Pedido de arquivo cancelado."))
            },"confirmar_"+operacao,mostrar+"\nPosso continuar?",true);
        }
        static string Assinatura(string path) {
            if(Directory.Exists(path)) { var d=new DirectoryInfo(path); return "d|"+d.CreationTimeUtc.Ticks+"|"+d.LastWriteTimeUtc.Ticks; }
            var f=new FileInfo(path); if(!f.Exists) throw new IOException();
            return "f|"+f.CreationTimeUtc.Ticks+"|"+f.LastWriteTimeUtc.Ticks+"|"+f.Length;
        }
        static bool Igual(string a,string b) { return String.Equals(a,b,StringComparison.OrdinalIgnoreCase); }
        static bool Dentro(string path,string root) { return path.StartsWith(root.TrimEnd(Path.DirectorySeparatorChar,Path.AltDirectorySeparatorChar)+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase); }
        public static string Canonico(string path) {
            if(String.IsNullOrWhiteSpace(path) || !Regex.IsMatch(path,@"^[a-zA-Z]:[\\/]")) throw new InvalidOperationException("Use uma pasta local do Windows, com caminho completo.");
            if(path.IndexOf(':',2)>=0 || path.StartsWith(@"\\")) throw new InvalidOperationException("Esse tipo de caminho não é suportado.");
            string full=Path.GetFullPath(path);
            return full.Length>3 ? full.TrimEnd(Path.DirectorySeparatorChar,Path.AltDirectorySeparatorChar) : full;
        }
        public static void ConferirAtalhos(string path) {
            string p=path;
            while(!String.IsNullOrEmpty(p)) {
                if((File.Exists(p) || Directory.Exists(p)) && (File.GetAttributes(p)&FileAttributes.ReparsePoint)!=0 && !ArquivoNuvem(p))
                    throw new InvalidOperationException("Essa localização contém um link ou atalho de pasta. Escolha a pasta real em Configurações → Arquivos.");
                var parent=Path.GetDirectoryName(p); if(parent==p) break; p=parent;
            }
        }
        string[] Raizes() { return (pastas() ?? new string[0]).Select(Canonico).Distinct(StringComparer.OrdinalIgnoreCase).ToArray(); }
        string Validar(string path) {
            path=Canonico(path);
            if(!Raizes().Any(r=>Igual(path,r) || Dentro(path,r))) throw new InvalidOperationException("Essa localização não está nas pastas escolhidas. Adicione-a em Configurações → Arquivos.");
            ConferirAtalhos(path); return path;
        }
        static string NomeSeguro(string nome) {
            if(String.IsNullOrWhiteSpace(nome) || nome=="." || nome==".." || nome.EndsWith(".") || nome.EndsWith(" ") || nome.IndexOfAny(Path.GetInvalidFileNameChars())>=0
                || Regex.IsMatch(nome,@"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)",RegexOptions.IgnoreCase))
                throw new InvalidOperationException("Use somente um nome de arquivo ou pasta, sem caminhos, símbolos reservados ou ponto no final.");
            return nome;
        }
        string Pasta(string nome) {
            var candidatos=PastasConhecidas(nome);
            if(candidatos.Count!=1) throw new InvalidOperationException("Não identifiquei uma única pasta. Se ela estiver fora do acesso atual, adicione-a em Configurações → Arquivos deste computador. Você também pode informar o caminho completo de uma pasta escolhida.");
            return candidatos[0];
        }
        List<string> PastasConhecidas(string nome) {
            nome=Regex.Replace((nome ?? "").Trim(),@"^(?:d[ao]s?|n[ao]s?|em|aos?|para)\s+","",RegexOptions.IgnoreCase);
            nome=Nome(Referencia(nome)); string f=Dobrar(nome);
            string alias=null;
            if(f=="documentos" || f=="meus documentos") alias=Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
            if(f=="area de trabalho" || f=="desktop") alias=Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            if(f=="downloads" || f=="download") alias=Downloads();
            if(alias!=null) { string p=Validar(alias); if(!Directory.Exists(p)) throw new IOException(); return new List<string> { p }; }
            if(Path.IsPathRooted(nome)) { string p=Validar(nome); if(!Directory.Exists(p)) throw new IOException(); return new List<string> { p }; }
            var roots=Raizes();
            var candidatos=roots.Where(r=>Dobrar(Path.GetFileName(r))==f).ToList();
            if(candidatos.Count==0) candidatos=roots.Select(r=>Path.Combine(r,nome)).Where(Directory.Exists).ToList();
            return candidatos.Select(Validar).ToList();
        }
        static int Separador(string text,string pattern) {
            bool aspas=false; int encontrado=-1;
            for(int i=0;i<text.Length;i++) {
                if(text[i]=='"' || text[i]=='“' || text[i]=='”') aspas=!aspas;
                if(!aspas && Regex.IsMatch(text.Substring(i),"^"+pattern,RegexOptions.IgnoreCase)) encontrado=i;
            }
            return encontrado;
        }
        void SepararLugar(string text,out string termo,out string lugar) {
            int i=Separador(text,@"\s+(?:em|na|no|nas|nos|dos|das)\s+");
            if(i<0) { termo=text; lugar=null; return; }
            var m=Regex.Match(text.Substring(i),@"^\s+(?:em|na|no|nas|nos|dos|das)\s+",RegexOptions.IgnoreCase);
            termo=text.Substring(0,i); lugar=text.Substring(i+m.Length);
        }
        List<string> Resolver(string referencia) {
            referencia=Referencia(referencia);
            string termo, lugar; SepararLugar(referencia,out termo,out lugar); termo=Nome(Referencia(termo));
            if(Path.IsPathRooted(termo)) {
                string p=Validar(termo); return File.Exists(p) || Directory.Exists(p) ? new List<string> { p } : new List<string>();
            }
            var conhecidas=PastasConhecidas(referencia);
            if(conhecidas.Count>0) return conhecidas;
            string[] roots=lugar==null ? Raizes() : new[] { Pasta(lugar) };
            var diretos=roots.Select(r=>Validar(Path.Combine(r,termo))).Where(p=>File.Exists(p) || Directory.Exists(p)).Distinct(StringComparer.OrdinalIgnoreCase).ToList();
            if(diretos.Count>0) return diretos;
            if(termo.Contains("\\") || termo.Contains("/") || termo.Contains(":")) return new List<string>();
            bool parcial=false; string f=Dobrar(termo);
            var encontrados=Ler(roots,true,ref parcial).Where(p=>Dobrar(Path.GetFileName(p))==f || Dobrar(Path.GetFileNameWithoutExtension(p))==f).ToList();
            if(parcial) throw new InvalidOperationException("A busca desse item foi parcial. Informe uma pasta mais específica ou o caminho completo. Se estiver fora do acesso atual, adicione a pasta em Configurações → Arquivos deste computador.");
            return encontrados;
        }
        List<string> Ler(IEnumerable<string> roots,bool recursivo,ref bool parcial) {
            var lista=new List<string>(); var fila=new Queue<string>(roots); var vistos=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var tempo=Stopwatch.StartNew(); int contagem=0;
            while(fila.Count>0 && contagem<10000 && tempo.Elapsed.TotalSeconds<5) {
                string dir=fila.Dequeue(); if(!vistos.Add(dir)) continue;
                try {
                    Validar(dir);
                    foreach(var p in Directory.EnumerateFileSystemEntries(dir)) {
                        contagem++;
                        if(contagem>10000 || tempo.Elapsed.TotalSeconds>=5) { parcial=true; break; }
                        if((File.GetAttributes(p)&FileAttributes.ReparsePoint)!=0 && !ArquivoNuvem(p)) { parcial=true; continue; }
                        lista.Add(p); if(recursivo && Directory.Exists(p)) fila.Enqueue(p);
                    }
                } catch(UnauthorizedAccessException) { parcial=true; } catch(IOException) { parcial=true; } catch(InvalidOperationException) { parcial=true; }
            }
            if(fila.Count>0) parcial=true;
            return lista;
        }
        static readonly string[] TiposAbriveis={".txt",".pdf",".doc",".docx",".xls",".xlsx",".csv",".ppt",".pptx",".rtf",".odt",".ods",".odp",".png",".jpg",".jpeg",".webp",".gif",".bmp",".mp3",".wav",".ogg",".mp4",".mkv",".mov"};
        static void Abrir(string path) {
            Process.Start(new ProcessStartInfo { FileName=path, UseShellExecute=true });
        }
        [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct DadosArquivo {
            public uint atributos,criadoBaixo,criadoAlto,acessoBaixo,acessoAlto,escritoBaixo,escritoAlto,tamanhoAlto,tamanhoBaixo,tag,reservado;
            [MarshalAs(UnmanagedType.ByValTStr,SizeConst=260)] public string nome;
            [MarshalAs(UnmanagedType.ByValTStr,SizeConst=14)] public string curto;
        }
        [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr FindFirstFile(string path,out DadosArquivo dados);
        [DllImport("kernel32.dll")] static extern bool FindClose(IntPtr handle);
        static bool ArquivoNuvem(string path) {
            DadosArquivo dados; var handle=FindFirstFile(path,out dados);
            if(handle==new IntPtr(-1)) return false;
            try { return (dados.tag & 0xFFFF0FFFu)==0x9000001Au || dados.tag==0x80000021u; }
            finally { FindClose(handle); }
        }
        static void Reciclar(string path) {
            // A Lixeira pede confirmação nativa se o volume não permitir reciclagem.
            if(Directory.Exists(path)) FileSystem.DeleteDirectory(path,UIOption.AllDialogs,RecycleOption.SendToRecycleBin,UICancelOption.ThrowException);
            else FileSystem.DeleteFile(path,UIOption.AllDialogs,RecycleOption.SendToRecycleBin,UICancelOption.ThrowException);
        }
        [DllImport("shell32.dll")] static extern int SHGetKnownFolderPath([MarshalAs(UnmanagedType.LPStruct)] Guid rfid,uint flags,IntPtr token,out IntPtr path);
        static string Downloads() {
            IntPtr p; int status=SHGetKnownFolderPath(new Guid("374DE290-123F-4565-9164-39C4925E467B"),0,IntPtr.Zero,out p);
            if(status!=0) return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),"Downloads");
            try { return Marshal.PtrToStringUni(p); } finally { Marshal.FreeCoTaskMem(p); }
        }
        public static string[] PastasPadrao() {
            return new[] { Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),Downloads(),Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory) }
                .Where(p=>!String.IsNullOrEmpty(p)).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        }
    }
}
