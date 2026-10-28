from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field


class GlossaryItem(BaseModel):
    id: int
    slug: str
    termo: str
    letra_inicial: str
    categoria: str
    definicao_curta: str
    formula_latex: Optional[str] = None


class GlossaryDetail(GlossaryItem):
    conteudo_markdown: str


class GlossaryResponse(BaseModel):
    total: int
    items: List[GlossaryItem]


class BookItem(BaseModel):
    id: int
    slug: str
    titulo: str
    subtitulo: Optional[str] = None
    autor: str
    ano_publicacao: Optional[int] = None
    nivel_dificuldade: str
    categoria: str
    resenha_markdown: str
    principais_licoes: List[str] = Field(default_factory=list)
    avaliacao_media: float


class ArticleItem(BaseModel):
    id: int
    slug: str
    titulo: str
    subtitulo: Optional[str] = None
    autor_nome: str
    categoria: str
    tags: List[str] = Field(default_factory=list)
    tempo_leitura_min: int
    is_premium: bool
    publicado_em: Optional[str] = None


class ArticleDetail(ArticleItem):
    conteudo_markdown: str



class SupportTicketCreate(BaseModel):
    nome_contato: str
    email_contato: EmailStr
    assunto: str
    mensagem: str


class SupportTicketResponse(BaseModel):
    id_ticket: int
    status: str
    mensagem_retorno: str
