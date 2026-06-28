import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
from datetime import date, timedelta

app = FastAPI()

# ─────────────────────────────────────────────────────────────────
#  CONEXÃO — usa DATABASE_URL (URI completa do Supabase Pooler).
#  Essa variável resolve o erro "no tenant identifier provided"
#  porque a URI já embute o project-ref no host:
#  postgresql://postgres.[project-ref]:[senha]@aws-...pooler.supabase.com:6543/postgres
#
#  Configure no painel da Render:
#  Key: DATABASE_URL
#  Value: (cole a "Connection string" > "URI" do Supabase, modo Transaction Pooler)
# ─────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError("Variável de ambiente DATABASE_URL não configurada.")
    return psycopg2.connect(DATABASE_URL, sslmode="require")


# ─────────────────────────────────────────────────────────────────
#  MODELOS PYDANTIC
# ─────────────────────────────────────────────────────────────────
class ProductModel(BaseModel):
    product_id: str

class CustomerModel(BaseModel):
    email: str

class KiwifyWebhook(BaseModel):
    status: str
    Product: ProductModel
    Customer: CustomerModel


# ─────────────────────────────────────────────────────────────────
#  MAPEAMENTO DE PRODUTOS
#  Adicione quantos IDs quiser dentro de cada lista.
# ─────────────────────────────────────────────────────────────────
IDS_MENSAL    = ["90bcae92-0b07-4919-aa0e-f34efcd6c6a5"]
IDS_ANUAL     = ["7f83238d-7f05-4f61-82e0-53d6a94e84c4"]
IDS_VITALICIO = ["1993e4d4-26ce-4969-af81-47cba5f51bc8"]


# ─────────────────────────────────────────────────────────────────
#  ROTA PRINCIPAL — ouve na raiz para evitar 404 em testes
# ─────────────────────────────────────────────────────────────────
@app.post("/")
async def webhook(data: KiwifyWebhook):
    email         = data.Customer.email.strip().lower()
    status_venda  = data.status.strip().lower()
    product_id    = str(data.Product.product_id).strip()

    conn = get_db_connection()
    cur  = conn.cursor()

    try:
        # ── Pagamento aprovado ────────────────────────────────────
        if status_venda == "approved":

            if product_id in IDS_MENSAL:
                tipo_licenca = "mensal"
                expira_em    = date.today() + timedelta(days=30)

            elif product_id in IDS_ANUAL:
                tipo_licenca = "anual"
                expira_em    = date.today() + timedelta(days=365)

            elif product_id in IDS_VITALICIO:
                tipo_licenca = "vitalicio"
                expira_em    = None   # NULL = acesso infinito

            else:
                return {
                    "status":  "ignored",
                    "message": f"Produto ID '{product_id}' não mapeado."
                }

            cur.execute("""
                INSERT INTO licencas_ativas (email, tipo_licenca, expira_em, criado_em)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (email)
                DO UPDATE SET
                    tipo_licenca = EXCLUDED.tipo_licenca,
                    expira_em    = EXCLUDED.expira_em;
            """, (email, tipo_licenca, expira_em))
            conn.commit()
            return {"status": "success", "plan_applied": tipo_licenca}

        # ── Reembolso ou Chargeback — remove acesso imediatamente ─
        elif status_venda in ["refunded", "chargedback"]:
            cur.execute(
                "DELETE FROM licencas_ativas WHERE email = %s;",
                (email,)
            )
            conn.commit()
            return {"status": "success", "message": "Acesso removido por reembolso/chargeback."}

        # ── Qualquer outro status é ignorado com segurança ────────
        return {"status": "ignored", "message": f"Status '{status_venda}' não é relevante."}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        cur.close()
        conn.close()
