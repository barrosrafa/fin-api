-- Local disposable security fixture. Schema contract only, never customer records.
CREATE TABLE IF NOT EXISTS core.usuario (
 id_usuario uuid PRIMARY KEY DEFAULT gen_random_uuid(), nome varchar(100) NOT NULL,
 email varchar(150) NOT NULL UNIQUE, cpf_cnpj varchar(14) UNIQUE,
 id_externo varchar(150) UNIQUE, role varchar(30) DEFAULT 'user', tier varchar(30) DEFAULT 'free',
 status varchar(20) DEFAULT 'Ativo', ultimo_acesso timestamp, data_cadastro timestamp DEFAULT now(),
 password_hash varchar(255), salt varchar(255)
);
CREATE TABLE IF NOT EXISTS core.carteira (
 id_carteira uuid PRIMARY KEY DEFAULT gen_random_uuid(), id_usuario uuid NOT NULL REFERENCES core.usuario(id_usuario) ON DELETE CASCADE,
 nome_carteira varchar(50) NOT NULL, principal boolean DEFAULT true, moeda varchar(3) DEFAULT 'BRL',
 status varchar(20) DEFAULT 'Ativa', data_criacao timestamp DEFAULT now()
);
