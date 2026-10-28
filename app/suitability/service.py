import json
from typing import List, Dict, Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.suitability.schemas import (
    SuitabilityQuestion,
    SuitabilityOption,
    SuitabilityEvaluateRequest,
    SuitabilityEvaluateResponse,
    AssetAllocationTarget,
)


class SuitabilityService:
    async def get_questions(self, db_session: AsyncSession) -> List[SuitabilityQuestion]:
        """
        Retrieves active questions and weighted options ordered by question index.
        """
        stmt = text(
            """
            SELECT p.id_pergunta, p.ordem as p_ordem, p.titulo, p.descricao, p.eixo_analise,
                   o.id_opcao, o.ordem as o_ordem, o.texto_resposta, o.pontuacao_peso
            FROM suitability.pergunta p
            JOIN suitability.opcao_resposta o ON o.id_pergunta = p.id_pergunta
            WHERE p.ativo = TRUE
            ORDER BY p.ordem ASC, o.ordem ASC;
            """
        )
        res = await db_session.execute(stmt)
        rows = res.mappings().all()

        questions_dict: dict[int, dict] = {}
        for r in rows:
            p_id = r["id_pergunta"]
            if p_id not in questions_dict:
                questions_dict[p_id] = {
                    "id_pergunta": p_id,
                    "ordem": r["p_ordem"],
                    "titulo": r["titulo"],
                    "descricao": r["descricao"],
                    "eixo": r["eixo_analise"],
                    "opcoes": [],
                }
            questions_dict[p_id]["opcoes"].append(
                SuitabilityOption(
                    id_opcao=r["id_opcao"],
                    ordem=r["o_ordem"],
                    texto=r["texto_resposta"],
                    pontos=r["pontuacao_peso"],
                )
            )

        return [SuitabilityQuestion(**q) for q in sorted(questions_dict.values(), key=lambda x: x["ordem"])]

    async def evaluate_answers(
        self, db_session: AsyncSession, request: SuitabilityEvaluateRequest
    ) -> SuitabilityEvaluateResponse:
        """
        Computes total score from selected options, queries matching risk category,
        and returns target allocation and customized recommendations.
        """
        if not request.respostas:
            raise HTTPException(status_code=400, detail="Nenhuma resposta fornecida")

        option_ids = [a.id_opcao_selecionada for a in request.respostas]
        stmt = text(
            """
            SELECT id_opcao, pontuacao_peso 
            FROM suitability.opcao_resposta 
            WHERE id_opcao = ANY(:ids);
            """
        )
        res = await db_session.execute(stmt, {"ids": option_ids})
        rows = res.mappings().all()

        score_map = {r["id_opcao"]: r["pontuacao_peso"] for r in rows}
        total_score = sum(score_map.get(op_id, 0) for op_id in option_ids)

        # Scale to 0-100 range based on 4 questions with max weight 10 each -> score * 2.5
        normalized_score = min(100, int(total_score * 2.5))

        # Query matching category
        cat_stmt = text(
            """
            SELECT codigo, nome, descricao, alocacao_alvo_json
            FROM suitability.categoria_risco
            WHERE :score BETWEEN score_min AND score_max
            LIMIT 1;
            """
        )
        cat_res = await db_session.execute(cat_stmt, {"score": normalized_score})
        cat_row = cat_res.mappings().first()

        if not cat_row:
            # Fallback based on boundaries
            if normalized_score <= 35:
                codigo = "CONSERVADOR"
                nome = "Perfil Conservador"
                desc = "Foco em preservação de capital e liquidez imediata com baixa tolerância a volatilidade."
                aloc = {"renda_fixa": 80, "fiis": 15, "acoes": 5, "internacional": 0}
            elif normalized_score <= 70:
                codigo = "MODERADO"
                nome = "Perfil Moderado"
                desc = "Equilíbrio entre segurança e geração de renda com dividendos."
                aloc = {"renda_fixa": 45, "fiis": 30, "acoes": 20, "internacional": 5}
            else:
                codigo = "ARROJADO"
                nome = "Perfil Arrojado"
                desc = "Foco em rentabilidade agressiva no longo prazo com tolerância a oscilações."
                aloc = {"renda_fixa": 15, "fiis": 25, "acoes": 40, "internacional": 15, "cripto": 5}
        else:
            codigo = cat_row["codigo"]
            nome = cat_row["nome"]
            desc = cat_row["descricao"]
            aloc = cat_row["alocacao_alvo_json"]
            if isinstance(aloc, str):
                aloc = json.loads(aloc)

        recomendacoes = [
            f"Priorize aportes na classe com maior desvio percentual em relação à sua meta de {aloc.get('acoes', 0)}% em ações.",
            "Reinvista os proventos recebidos mensalmente para acelerar o efeito de juros compostos.",
            "Revise seu suitability anualmente ou caso ocorra mudança relevante em sua renda ou horizonte.",
        ]

        return SuitabilityEvaluateResponse(
            score_total=normalized_score,
            codigo_categoria=codigo,
            nome_categoria=nome,
            descricao=desc,
            alocacao_alvo=AssetAllocationTarget(
                renda_fixa=float(aloc.get("renda_fixa", 0)),
                fiis=float(aloc.get("fiis", 0)),
                acoes=float(aloc.get("acoes", 0)),
                internacional=float(aloc.get("internacional", 0)),
                cripto=float(aloc.get("cripto", 0)),
            ),
            recomendacoes_principais=recomendacoes,
        )
