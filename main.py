import os
from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel
import psycopg2
from datetime import date, timedelta

app = FastAPI()

# Puxa os dados de conexão do Supabase das variáveis de ambiente da Render
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS")
DB_PORT = os.getenv("DB_PORT", "5432")

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST, database=DB_NAME, user=DB_USER, 
        password=DB_PASS, port=DB_PORT, sslmode="require"
    )

class ProductModel(BaseModel):
    product_id: str

class CustomerModel(BaseModel):
    email: str

class KiwifyWebhook(BaseModel):
    status: str
    Product: ProductModel
    Customer: CustomerModel

@app.post("/kiwify")
async def webhook(data: KiwifyWebhook):
    email = data.Customer.email.strip().lower()
    status_venda = data.status.strip().lower()
    product_id = str(data.Product.product_id).strip()
    
    # ⚠️ Troque pelos IDs reais da sua Kiwify
    ID_PLANO_ANUAL = "123456"      
    ID_PLANO_VITALICIO = "789101"  

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        if status_venda == "approved":
            if product_id == ID_PLANO_ANUAL:
                tipo_licenca = "assinatura"
                expira_em = date.today() + timedelta(days=365)
            elif product_id == ID_PLANO_VITALICIO:
                tipo_licenca = "vitalicio"
                expira_em = None
            else:
                return {"status": "ignored", "message": "Produto invalido"}

            query = """
                INSERT INTO licencas_ativas (email, tipo_licenca, expira_em, criado_em)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (email) 
                DO UPDATE SET tipo_licenca = EXCLUDED.tipo_licenca, expira_em = EXCLUDED.expira_em;
            """
            cur.execute(query, (email, tipo_licenca, expira_em))
            conn.commit()
            return {"status": "success"}

        elif status_venda in ["refunded", "chargedback"]:
            cur.execute("DELETE FROM licencas_ativas WHERE email = %s;", (email,))
            conn.commit()
            return {"status": "success"}

        return {"status": "ignored"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
