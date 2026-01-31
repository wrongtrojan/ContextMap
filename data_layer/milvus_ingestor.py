import os
import json
import yaml
from pymilvus import connections, FieldSchema, CollectionSchema, DataType, Collection, utility

class MilvusIngestor:
    def __init__(self, force_reset=False):
        # 1. 加载双配置
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.join(current_dir, "../configs")
        
        with open(os.path.join(config_dir, "model_config.yaml"), 'r', encoding='utf-8') as f:
            self.model_cfg = yaml.safe_load(f)
        with open(os.path.join(config_dir, "milvus_config.yaml"), 'r', encoding='utf-8') as f:
            self.db_cfg = yaml.safe_load(f)
        
        # 2. 连接 Milvus
        conn = self.db_cfg['connection']
        connections.connect("default", host=conn['host'], port=conn['port'])
        
        self.col_name = self.db_cfg['collection']['name']
        
        # 强制重置逻辑
        if force_reset and utility.has_collection(self.col_name):
            utility.drop_collection(self.col_name)
            print(f"警告: 已强制删除并重置旧集合 {self.col_name}")

        self._setup_collection()

    def _setup_collection(self):
        """定义 Schema 并加载索引"""
        if utility.has_collection(self.col_name):
            self.collection = Collection(self.col_name)
            self.collection.load()
            return

        s = self.db_cfg['schema']
        c = self.db_cfg['collection']

        fields = [
            FieldSchema(name=s['pk'], dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name=s['doc'], dtype=DataType.VARCHAR, max_length=500),
            FieldSchema(name=s['page'], dtype=DataType.INT64),
            FieldSchema(name=s['image'], dtype=DataType.VARCHAR, max_length=200),
            FieldSchema(name=s['text'], dtype=DataType.VARCHAR, max_length=4000), 
            FieldSchema(name=s['vec'], dtype=DataType.FLOAT_VECTOR, dim=c['dim'])
        ]
        
        schema = CollectionSchema(fields, "Multimodal Asset Alignment Collection")
        self.collection = Collection(self.col_name, schema)

        index_params = {
            "metric_type": c['metric_type'],
            "index_type": c['index_type'],
            "params": {"nlist": c['nlist']}
        }
        self.collection.create_index(field_name=s['vec'], index_params=index_params)
        self.collection.load()
        print(f"新集合 {self.col_name} 创建并加载完成。")

    def _is_doc_already_ingested(self, doc_name):
        """增量检查"""
        s = self.db_cfg['schema']
        res = self.collection.query(
            expr=f'{s["doc"]} == "{doc_name}"',
            output_fields=[s['pk']],
            limit=1
        )
        return len(res) > 0

    def run_ingestion(self):
        """带有仪式感的入库流程"""
        processed_root = os.path.join(self.model_cfg['paths']['processed_storage'], "magic-pdf")
        
        if not os.path.exists(processed_root):
            print("错误：找不到加工数据根目录。")
            return

        total_new_docs = 0
        
        for doc_name in os.listdir(processed_root):
            doc_dir = os.path.join(processed_root, doc_name)
            if not os.path.isdir(doc_dir): continue
            
            manifest_path = os.path.join(doc_dir, "final_ingestion_manifest.json")
            
            if os.path.exists(manifest_path):
                # 增量检测
                if self._is_doc_already_ingested(doc_name):
                    print(f"跳过已入库文档: {doc_name}")
                    continue

                print(f"正在入库新文档: {doc_name} ...")
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if not data: continue

                # 插入数据 (顺序与 Schema 严格一致)
                entities = [
                    [item['doc_name'] for item in data],
                    [item['page_num'] for item in data],
                    [item['image_name'] for item in data],
                    [item['text_context'] for item in data],
                    [item['vector'] for item in data]
                ]
                self.collection.insert(entities)
                total_new_docs += 1
                print(f"入库成功: {doc_name} (对齐了 {len(data)} 条实体数据)")
            else:
                print(f"未发现清单文件，跳过: {doc_name}")

        self.collection.flush()
        print(f"--- 处理完成！本次新入库了 {total_new_docs} 个文档的数据 ---")

if __name__ == "__main__":
    # 由于我们增加了 page_num，第一次请保持为 True 以刷新数据库结构
    ingestor = MilvusIngestor(force_reset=False)
    ingestor.run_ingestion()