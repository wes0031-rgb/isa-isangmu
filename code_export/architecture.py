"""MoveWise System Architecture Diagram.

Generates `movewise_architecture.png` in the same folder.
Run: python3 architecture.py
"""
from diagrams import Diagram, Cluster, Edge
from diagrams.azure.compute import AppServices
from diagrams.azure.ml import CognitiveServices
from diagrams.azure.storage import BlobStorage
from diagrams.azure.database import DataExplorerClusters
from diagrams.onprem.client import Users
from diagrams.programming.language import Python
from diagrams.generic.network import Firewall


GRAPH_ATTR = {
    "fontsize": "34",
    "fontname": "Helvetica-Bold",
    "bgcolor": "white",
    "pad": "1.6",
    "nodesep": "1.1",
    "ranksep": "1.8",
    "dpi": "130",
    "splines": "spline",
    "rankdir": "TB",
    "compound": "true",
}

NODE_ATTR = {
    "fontsize": "15",
    "fontname": "Helvetica",
}

EDGE_ATTR = {
    "fontsize": "14",
    "fontname": "Helvetica-Bold",
    "penwidth": "2.5",
}

INGEST_CLUSTER = {
    "bgcolor": "#FFF4E6",
    "style": "rounded,filled",
    "fontsize": "22",
    "fontname": "Helvetica-Bold",
    "fontcolor": "#B25900",
    "pencolor": "#FFB266",
    "penwidth": "2.5",
    "margin": "24",
    "labeljust": "l",
}

AZURE_CLUSTER = {
    "bgcolor": "#E8F1FB",
    "style": "rounded,filled",
    "fontsize": "26",
    "fontname": "Helvetica-Bold",
    "fontcolor": "#003A75",
    "pencolor": "#5B9BD5",
    "penwidth": "2.5",
    "margin": "28",
    "labeljust": "l",
}

SUB_COMPUTE = {
    "bgcolor": "#FFFFFF",
    "style": "rounded,filled",
    "fontsize": "17",
    "fontname": "Helvetica-Bold",
    "fontcolor": "#003A75",
    "pencolor": "#9BC2E6",
    "penwidth": "1.5",
    "margin": "16",
}

SUB_AI = {
    "bgcolor": "#F5FAFF",
    "style": "rounded,filled",
    "fontsize": "17",
    "fontname": "Helvetica-Bold",
    "fontcolor": "#003A75",
    "pencolor": "#9BC2E6",
    "penwidth": "1.5",
    "margin": "16",
}

SUB_STORAGE = {
    "bgcolor": "#EAF6EA",
    "style": "rounded,filled",
    "fontsize": "17",
    "fontname": "Helvetica-Bold",
    "fontcolor": "#1F6B1F",
    "pencolor": "#9ACD9A",
    "penwidth": "1.5",
    "margin": "16",
}


with Diagram(
    "MoveWise — System Architecture",
    filename="/Users/sa/Desktop/2차프로젝트/movewise_architecture",
    outformat="png",
    show=False,
    direction="TB",
    graph_attr=GRAPH_ATTR,
    node_attr=NODE_ATTR,
    edge_attr=EDGE_ATTR,
):

    # ===== CLIENT =====
    user = Users("사용자\n(Mobile / Web)")

    # ===== BATCH INGESTION (leftmost) =====
    with Cluster("① Data Ingestion (Batch)", graph_attr=INGEST_CLUSTER):
        law_api = Firewall("국가법령정보\nOpen API")
        easylaw_api = Firewall("생활법령정보\nAPI")
        gov24 = Firewall("정부24\n(반자동)")
        ingest = Python("ingest_*.py\n청킹 + 메타")

        law_api >> Edge(color="#B25900") >> ingest
        easylaw_api >> Edge(color="#B25900") >> ingest
        gov24 >> Edge(color="#B25900") >> ingest

    # ===== AZURE PLATFORM =====
    with Cluster("② Azure Platform", graph_attr=AZURE_CLUSTER):

        with Cluster("API Layer", graph_attr=SUB_COMPUTE):
            app = AppServices(
                "App Service\nFastAPI\n\n/checklist\n/safecontract"
            )

        with Cluster("AI Services", graph_attr=SUB_AI):
            openai = CognitiveServices("Azure OpenAI\nGPT-4o")
            doc_intel = CognitiveServices("Document\nIntelligence")
            search = CognitiveServices("Azure\nAI Search")

        with Cluster("Storage & Indexes", graph_attr=SUB_STORAGE):
            blob = BlobStorage("Blob Storage\n원본 문서")
            idx_a = DataExplorerClusters("Index A\n법률 조문\n150~250")
            idx_b = DataExplorerClusters("Index B\n행정 절차\n30~50")

    # ===== INGESTION FLOW (orange) =====
    ingest >> Edge(color="#CC7A00", style="bold", label="upload") >> blob
    blob >> Edge(color="#CC7A00", style="bold") >> doc_intel
    doc_intel >> Edge(color="#CC7A00", style="bold", label="인덱싱") >> idx_a
    doc_intel >> Edge(color="#CC7A00", style="bold") >> idx_b

    # ===== USER ENTRY (blue) =====
    user >> Edge(color="#1F6FD0", style="bold", label="HTTPS", penwidth="3") >> app

    # ===== CHECKLIST FLOW (blue) =====
    app >> Edge(color="#1F6FD0", style="bold", label="① 쿼리 생성") >> openai
    openai >> Edge(color="#1F6FD0", style="bold", label="② 검색") >> search
    search >> Edge(color="#1F6FD0", style="bold", label="③ 청크 조회") >> idx_b

    # ===== SAFECONTRACT FLOW (green) =====
    app >> Edge(color="#2E8B57", style="bold", label="PDF / 사진") >> doc_intel
    doc_intel >> Edge(color="#2E8B57", style="bold", label="OCR") >> openai
    openai >> Edge(color="#2E8B57", style="bold", label="법률 RAG") >> idx_a
