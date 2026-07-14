"""添加 tb_resume 缺失列"""

from sqlalchemy import text

from app.core.database import engine

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE tb_resume ADD COLUMN optimized_content TEXT COMMENT '优化版简历内容(Markdown)'"))
        print("ADD COLUMN optimized_content: OK")
    except Exception as e:
        print(f"optimized_content: {e}")

    try:
        conn.execute(text("ALTER TABLE tb_resume ADD COLUMN optimized_at DATETIME COMMENT '优化时间'"))
        print("ADD COLUMN optimized_at: OK")
    except Exception as e:
        print(f"optimized_at: {e}")

    conn.commit()
    print("Done")
