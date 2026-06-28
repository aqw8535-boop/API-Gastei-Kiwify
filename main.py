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

# Mude a sua função no arquivo para usar a URL direta que mata esse erro do Supabase
DATABASE_URL = os.getenv("DATABASE_URL") # Você pode criar essa variável no Render com a string do Supabase

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")
class ProductModel(BaseModel):
    product_id: str

class CustomerModel(BaseModel):
    email: str

class KiwifyWebhook(BaseModel):
    status: str
    Product: ProductModel
    Customer: CustomerModel

@app.post("/")
async def webhook(data: KiwifyWebhook):
    email = data.Customer.email.strip().lower()
    status_venda = data.status.strip().lower()
    product_id = str(data.Product.product_id).strip()
    
    # 🛠️ ABAIXO VOCÊ SÓ PRECISA ADICIONAR OS IDS DA KIWIFY SEPARADOS POR VÍRGULA
    # Pode colocar quantos IDs antigos e novos quiser dentro dos colchetes!
    IDS_MENSAL = ["90bcae92-0b07-4919-aa0e-f34efcd6c6a5"]
    IDS_ANUAL = ["7f83238d-7f05-4f61-82e0-53d6a94e84c4"]      
    IDS_VITALICIO = ["1993e4d4-26ce-4969-af81-47cba5f51bc8"]  

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Se a Kiwify avisar que o pagamento foi aprovado
        if status_venda == "approved":
            
            # 1. Checa se o ID pertence a algum plano MENSAL
            if product_id in IDS_MENSAL:
                tipo_licenca = "mensal"
                expira_em = date.today() + timedelta(days=30)
                
            # 2. Checa se o ID pertence a algum plano ANUAL
            elif product_id in IDS_ANUAL:
                tipo_licenca = "anual"
                expira_em = date.today() + timedelta(days=365)
                
            # 3. Checa se o ID pertence a algum plano VITALÍCIO
            elif product_id in IDS_VITALICIO:
                tipo_licenca = "vitalicio"
                expira_em = None # Fica NULL no banco, acesso infinito
                
            # Se a Kiwify mandar um ID que você não cadastrou nas listas acima
            else:
                return {"status": "ignored", "message": f"Produto ID {product_id} nao mapeado"}

            # Faz o Insert ou Update atualizando o plano e a nova data de expiracao
            query = """
                INSERT INTO licencas_ativas (email, tipo_licenca, expira_em, criado_em)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (email) 
                DO UPDATE SET tipo_licenca = EXCLUDED.tipo_licenca, expira_em = EXCLUDED.expira_em;
            """
            cur.execute(query, (email, tipo_licenca, expira_em))
            conn.commit()
            return {"status": "success", "plan_applied": tipo_licenca}

        # Se o cliente pedir reembolso ou a operadora der Chargeback, remove o acesso
        elif status_venda in ["refunded", "chargedback"]:
            cur.execute("DELETE FROM licencas_ativas WHERE email = %s;", (email,))
            conn.commit()
            return {"status": "success", "message": "Acesso removido por reembolso"}

        return {"status": "ignored", "message": "Status nao relevante"}
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
