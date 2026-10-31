from app.core.database import bind_auth_email
import json
from typing import List, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.cms.schemas import (
    GlossaryItem,
    GlossaryDetail,
    GlossaryResponse,
    BookItem,
    ArticleItem,
    ArticleDetail,
    SupportTicketCreate,
    SupportTicketResponse,
)


class CMSService:
    async def get_glossary(
        self,
        db_session: AsyncSession,
        letter: Optional[str] = None,
        q: Optional[str] = None,
    ) -> GlossaryResponse:
        clauses = []
        params = {}
        if letter:
            clauses.append("letra_inicial = :letter")
            params["letter"] = letter.upper()
        if q:
            clauses.append("(termo ILIKE :q OR definicao_curta ILIKE :q)")
            params["q"] = f"%{q}%"

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        stmt = text(
            f"""
            SELECT id_termo, slug, termo, letra_inicial, categoria, definicao_curta, formula_latex
            FROM cms.termo_glossario
            {where_clause}
            ORDER BY termo ASC;
            """
        )
        res = await db_session.execute(stmt, params)
        rows = res.mappings().all()

        items = [
            GlossaryItem(
                id=r["id_termo"],
                slug=r["slug"],
                termo=r["termo"],
                letra_inicial=r["letra_inicial"],
                categoria=r["categoria"],
                definicao_curta=r["definicao_curta"],
                formula_latex=r["formula_latex"],
            )
            for r in rows
        ]
        return GlossaryResponse(total=len(items), items=items)

    async def get_glossary_term(self, db_session: AsyncSession, slug: str) -> GlossaryDetail:
        stmt = text(
            """
            SELECT id_termo, slug, termo, letra_inicial, categoria, definicao_curta, conteudo_markdown, formula_latex
            FROM cms.termo_glossario
            WHERE slug = :slug;
            """
        )
        res = await db_session.execute(stmt, {"slug": slug})
        r = res.mappings().first()
        if not r:
            raise HTTPException(status_code=404, detail="Termo não encontrado")

        return GlossaryDetail(
            id=r["id_termo"],
            slug=r["slug"],
            termo=r["termo"],
            letra_inicial=r["letra_inicial"],
            categoria=r["categoria"],
            definicao_curta=r["definicao_curta"],
            formula_latex=r["formula_latex"],
            conteudo_markdown=r["conteudo_markdown"],
        )

    async def get_books(self, db_session: AsyncSession, category: Optional[str] = None) -> List[BookItem]:
        where_clause = "WHERE categoria = :cat" if category else ""
        params = {"cat": category} if category else {}
        stmt = text(
            f"""
            SELECT id_livro, slug, titulo, subtitulo, autor, ano_publicacao, nivel_dificuldade,
                   categoria, resenha_markdown, principais_licoes, avaliacao_media
            FROM cms.livro_investimento
            {where_clause}
            ORDER BY avaliacao_media DESC;
            """
        )
        res = await db_session.execute(stmt, params)
        rows = res.mappings().all()

        books = []
        for r in rows:
            licoes = r["principais_licoes"]
            if isinstance(licoes, str):
                try:
                    licoes = json.loads(licoes)
                except Exception:
                    licoes = []
            elif not isinstance(licoes, list):
                licoes = []

            books.append(
                BookItem(
                    id=r["id_livro"],
                    slug=r["slug"],
                    titulo=r["titulo"],
                    subtitulo=r["subtitulo"],
                    autor=r["autor"],
                    ano_publicacao=r["ano_publicacao"],
                    nivel_dificuldade=r["nivel_dificuldade"],
                    categoria=r["categoria"],
                    resenha_markdown=r["resenha_markdown"],
                    principais_licoes=licoes,
                    avaliacao_media=float(r["avaliacao_media"]),
                )
            )
        return books

    async def get_articles(self, db_session: AsyncSession, limit: int = 10) -> List[ArticleItem]:
        stmt = text(
            """
            SELECT id_artigo, slug, titulo, subtitulo, autor_nome, categoria, tags,
                   tempo_leitura_min, is_premium, to_char(publicado_em, 'YYYY-MM-DD') as dt_pub
            FROM cms.artigo_blog
            ORDER BY created_at DESC
            LIMIT :limit;
            """
        )
        # Note: if table is empty, return empty list or fallback
        try:
            res = await db_session.execute(stmt, {"limit": limit})
            rows = res.mappings().all()
            if rows:
                return [
                    ArticleItem(
                        id=r["id_artigo"],
                        slug=r["slug"],
                        titulo=r["titulo"],
                        subtitulo=r["subtitulo"],
                        autor_nome=r["autor_nome"],
                        categoria=r["categoria"],
                        tags=r["tags"] or [],
                        tempo_leitura_min=r["tempo_leitura_min"],
                        is_premium=r["is_premium"],
                        publicado_em=r["dt_pub"],
                    )
                    for r in rows
                ]
            return [
                ArticleItem(
                    id=1,
                    slug="como-analisar-bancos-margem-financeira-basileia",
                    titulo="Como Analisar Ações de Bancos na B3",
                    subtitulo="Entenda Índice de Basileia, Margem Financeira Líquida e Custo de Crédito",
                    autor_nome="Equipe de Análise Quantitativa",
                    categoria="AÇÕES",
                    tags=["Bancos", "Valuation", "Basileia"],
                    tempo_leitura_min=8,
                    is_premium=False,
                    publicado_em="2026-10-25",
                ),
                ArticleItem(
                    id=2,
                    slug="tributacao-reits-dividendos-ir-30-por-cento",
                    titulo="Tributação de REITs Americanos para Brasileiros",
                    subtitulo="O impacto do Withholding Tax de 30% do IRS e como calcular o Yield Líquido Real",
                    autor_nome="Mesa Internacional",
                    categoria="REITS",
                    tags=["REITs", "Tributação", "IRS"],
                    tempo_leitura_min=6,
                    is_premium=True,
                    publicado_em="2026-10-20",
                ),
            ]
        except Exception:
            return []

    async def get_article_by_slug(self, db_session: AsyncSession, slug: str) -> Optional[ArticleDetail]:
        stmt = text(
            """
            SELECT id_artigo, slug, titulo, subtitulo, autor_nome, categoria, tags,
                   tempo_leitura_min, is_premium, to_char(publicado_em, 'YYYY-MM-DD') as dt_pub,
                   conteudo_markdown
            FROM cms.artigo_blog
            WHERE slug = :slug
            LIMIT 1;
            """
        )
        try:
            res = await db_session.execute(stmt, {"slug": slug})
            row = res.mappings().first()
            if row:
                return ArticleDetail(
                    id=row["id_artigo"],
                    slug=row["slug"],
                    titulo=row["titulo"],
                    subtitulo=row["subtitulo"],
                    autor_nome=row["autor_nome"],
                    categoria=row["categoria"],
                    tags=row["tags"] or [],
                    tempo_leitura_min=row["tempo_leitura_min"],
                    is_premium=row["is_premium"],
                    publicado_em=row["dt_pub"],
                    conteudo_markdown=row["conteudo_markdown"] or "",
                )
        except Exception:
            pass
        return None

    async def create_support_ticket(self, db_session: AsyncSession, ticket: SupportTicketCreate) -> SupportTicketResponse:
        await bind_auth_email(db_session, ticket.email_contato)
        stmt = text(
            """
            INSERT INTO cms.ticket_suporte (nome_contato, email_contato, assunto, mensagem)
            VALUES (:nome, :email, :assunto, :mensagem)
            RETURNING id_ticket;
            """
        )
        res = await db_session.execute(
            stmt,
            {
                "nome": ticket.nome_contato,
                "email": ticket.email_contato,
                "assunto": ticket.assunto,
                "mensagem": ticket.mensagem,
            },
        )
        ticket_id = res.scalar()
        await db_session.commit()
        return SupportTicketResponse(
            id_ticket=ticket_id,
            status="ABERTO",
            mensagem_retorno="Chamado registrado com sucesso. Nossa equipe responderá em até 24 horas úteis.",
        )
