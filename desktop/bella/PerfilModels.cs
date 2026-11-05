using System;

namespace Bella {
    public sealed class PerfilDesktop {
        public string origem { get; set; }
        public string modelo_id { get; set; }
        public string nome { get; set; }
        public string foto_id { get; set; }
        public string foto { get; set; }
        public bool inalterada { get; set; }
    }

    // A foto remota só vive na memória; nunca sobrescreve a foto local do legado.
    public sealed class RetratoModels {
        public string Origem { get; private set; }
        public string ModeloId { get; private set; }
        public string Nome { get; private set; }
        public string FotoId { get; private set; }
        public string Foto { get; private set; }
        public bool Remoto { get { return Origem!="legado"; } }
        public RetratoModels() { Limpar(); }
        public void Limpar() { Origem="pendente"; ModeloId=null; Nome=null; FotoId=null; Foto=null; }
        public void Aplicar(PerfilDesktop p) {
            if(p==null || (p.origem!="legado" && p.origem!="models")) throw new InvalidOperationException("Perfil indisponível.");
            if(p.origem=="legado") { Limpar(); Origem="legado"; Nome="Bella"; FotoId="legado"; return; }
            Guid id;
            if(!Guid.TryParse(p.modelo_id,out id) || String.IsNullOrEmpty(p.foto_id) || !p.foto_id.StartsWith(p.modelo_id+":",StringComparison.Ordinal))
                throw new InvalidOperationException("Identidade da foto inválida.");
            if(p.inalterada && (ModeloId!=p.modelo_id || FotoId!=p.foto_id)) throw new InvalidOperationException("Atualize a foto desta modelo.");
            if(!p.inalterada && p.foto!=null) Bella.Foto.Decodificar(p.foto,2*1024*1024);
            if(!p.inalterada) Foto=p.foto;
            Origem=p.origem; ModeloId=p.modelo_id; Nome=p.nome; FotoId=p.foto_id;
        }
    }
}
