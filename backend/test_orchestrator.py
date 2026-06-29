import os
import sys
from dotenv import load_dotenv

# Add backend to path so we can run directly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from analytics.orchestrator import MasterOrchestrator

def test_orchestrator():
    print("Testing Master Orchestrator...")
    
    if not os.getenv("GROQ_API_KEY"):
        print("GROQ_API_KEY is not set. Skipping execution test.")
        return

    orchestrator = MasterOrchestrator()

    # Test query routing
    query = "Clean the partner transaction ledger and perform risk anomaly scan for partner P-1002"
    print(f"\nRouting query: '{query}'")
    routed_claws = orchestrator.route_query(query)
    print(f"Routed claws: {routed_claws}")

    assert "data_analyst" in routed_claws or "anomaly_detection" in routed_claws, "Routing failed to identify correct Claws"

    # Test full pipeline execution
    print("\nExecuting full pipeline for query...")
    result = orchestrator.run_pipeline(query)
    
    print("\n--- Pipeline Execution Output ---")
    print(f"Active Claws: {result['active_claws']}")
    print(f"Sources retrieved: {len(result['sources'])}")
    print(f"Answer snippet (first 300 chars):\n{result['answer'][:300]}...")
    print("---------------------------------")
    print("Orchestrator test complete!")

if __name__ == "__main__":
    test_orchestrator()
