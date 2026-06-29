import os
import json
import traceback
from typing import List, Dict, Any, Tuple
from groq import Groq
from search.vector_store import search_faiss, get_document_metadata

# Claws configurations
CLAW_METADATA = {
    "data_analyst": {
        "name": "Data Analyst Claw",
        "role": "Raw Data Specialist & Processor",
        "description": "Retrieves raw datasets, performs cleaning/normalization, conducts EDA, and calculates baseline KPIs.",
        "protocol": (
            "1. Retrieve raw datasets via RAG context.\n"
            "2. Identify missing values, duplicates, and format anomalies.\n"
            "3. Run exploratory data analysis to identify core trends/anomalies.\n"
            "4. Calculate foundational KPIs relevant to the dataset."
        ),
        "output_structure": (
            "Standardized Markdown report containing:\n"
            "- | Data Quality Metrics |\n"
            "- | Core Trends Identified |\n"
            "- | Calculated KPIs |\n"
            "- | Structured Insight Summary |"
        )
    },
    "kpi_monitoring": {
        "name": "KPI Monitoring Claw",
        "role": "Metric Sentinel & Diagnostic Analyst",
        "description": "Compares KPIs against historical baselines, detects significant variances, and formulates diagnostic hypotheses.",
        "protocol": (
            "1. Ingest calculated KPIs and compare them against historical baselines or targets.\n"
            "2. Detect statistically significant variances, spikes, or drops.\n"
            "3. Formulate hypotheses explaining why the change occurred by cross-referencing context."
        ),
        "output_structure": (
            "- `[Metric Delta Alert]` Alert banner showing the metric change details.\n"
            "- `[Root Cause Analysis Hypothesis]` Structured reasoning on the triggers of the variance.\n"
            "- `[Recommended Follow-up Actions]` Diagnostic steps to verify hypothesis."
        )
    },
    "anomaly_detection": {
        "name": "Anomaly Detection Claw",
        "role": "Operational & Financial Risk Guard",
        "description": "Scans data arrays for outliers, exceptions, pattern deviations, and categorizes risks.",
        "protocol": (
            "1. Scan transactional, partner, or operational data arrays.\n"
            "2. Flag outliers, pattern deviations, or exceptions based on statistical thresholds or rules.\n"
            "3. Categorize risks (Low, Medium, High)."
        ),
        "output_structure": (
            "A structured ledger table of exceptions detailing:\n"
            "| Timestamp/ID | Observed Behavior | Expected Baseline | Risk Level | Immediate Mitigation Step |"
        )
    },
    "customer_segmentation": {
        "name": "Customer Segmentation Claw",
        "role": "Behavioral & Cohort Demographer",
        "description": "Segments populations using attributes and defines personas with distinct traits and value drivers.",
        "protocol": (
            "1. Analyze user, customer, partner, or micro-entrepreneur data vectors.\n"
            "2. Segment populations using behavioral, demographic, or transactional attributes.\n"
            "3. Define clear personas for each segment, explaining distinct traits and value drivers."
        ),
        "output_structure": (
            "A comparative profile matrix mapping out:\n"
            "| Segment Name | Size/Percentage | Defining Behavioral DNA | Tailored Engagement Strategy |"
        )
    },
    "business_performance": {
        "name": "Business Performance Claw",
        "role": "Executive Synthesizer & Strategic Advisor",
        "description": "Aggregates inputs from other Claws, synthesizes data into macro takeaways, risk registry, and owner-assignable tasks.",
        "protocol": (
            "1. Aggregate outputs from the Data Analyst, KPI, and Anomaly Claws for a specified cadence (Daily/Weekly).\n"
            "2. Synthesize data into a high-level executive summary."
        ),
        "output_structure": (
            "- **Executive Pulse:** Top 3-5 macro takeaways.\n"
            "- **Risk Registry:** Blocker items or negative trends caught by Anomaly Claw.\n"
            "- **Strategic Next Actions:** Prioritized, owner-assignable tasks based on findings."
        )
    }
}

class MasterOrchestrator:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY environment variable is required.")
        self.client = Groq(api_key=self.api_key)
        self.model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    def route_query(self, query: str) -> List[str]:
        """
        Determines which Claws are required to fulfill the user's request.
        Returns a list of claw IDs in order of execution.
        """
        system_prompt = f"""You are the routing engine of the Master Orchestrator of an advanced analytical ecosystem.
Your job is to analyze the user's input query and determine which of the 5 specialized analytical "Claws" are required to fulfill the request, and in what order.

Available Claws:
1. `data_analyst`: Raw Data Specialist. Call this if the query asks for cleaning, parsing, calculation of baseline KPIs, or general data trends.
2. `kpi_monitoring`: Diagnostic Analyst. Call this if the query asks to compare KPIs to benchmarks, analyze deltas/drops, or formulate hypotheses for KPI changes.
3. `anomaly_detection`: Risk & Outlier Sentinel. Call this if the query asks to scan for outliers, check error rates, fraud, chargebacks, drop-offs, or log operational exceptions.
4. `customer_segmentation`: Customer/Partner Behavior. Call this if the query asks to group, cluster, segment users/partners/customers, or define cohorts/personas.
5. `business_performance`: Executive Synthesizer. Call this if the query requires a high-level executive pulse, a risk registry, or strategic recommendations aggregating other claws.

Rules:
1. Respond ONLY with a JSON list of strings representing the active claw IDs in execution order. Example: ["data_analyst", "anomaly_detection"]
2. Do not include any explanation or formatting outside the JSON list.
3. If sequential execution is needed (e.g. clean data and then segment), ensure the prerequisite claw (data_analyst) is first.
4. Default to ordering: data_analyst -> kpi_monitoring -> anomaly_detection -> customer_segmentation -> business_performance. Only include the claws that are actually relevant.

Query: "{query}"
JSON Output:"""

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": system_prompt}],
                temperature=0.0,
                max_tokens=64
            )
            content = completion.choices[0].message.content.strip()
            # Clean possible markdown wrap
            if content.startswith("```"):
                content = content.replace("```json", "").replace("```", "").strip()
            
            claws = json.loads(content)
            if isinstance(claws, list):
                # Validate values
                valid_claws = [c for c in claws if c in CLAW_METADATA]
                if valid_claws:
                    return valid_claws
        except Exception as e:
            print(f"Error routing query: {e}")
            traceback.print_exc()

        # Fallback if routing fails: run all claws that look relevant based on simple keywords
        fallback = []
        q_lower = query.lower()
        if "data" in q_lower or "trend" in q_lower or "kpi" in q_lower or "performance" in q_lower or "ledger" in q_lower:
            fallback.append("data_analyst")
        if "delta" in q_lower or "drop" in q_lower or "compare" in q_lower or "why" in q_lower:
            fallback.append("kpi_monitoring")
        if "anomaly" in q_lower or "risk" in q_lower or "outlier" in q_lower or "exception" in q_lower or "chargeback" in q_lower or "refund" in q_lower:
            fallback.append("anomaly_detection")
        if "segment" in q_lower or "cohort" in q_lower or "persona" in q_lower:
            fallback.append("customer_segmentation")
        if "executive" in q_lower or "strategic" in q_lower or "summary" in q_lower or "recommendation" in q_lower:
            fallback.append("business_performance")

        if not fallback:
            fallback = ["data_analyst"]
        
        # Sort fallback by standard execution pipeline order
        order = ["data_analyst", "kpi_monitoring", "anomaly_detection", "customer_segmentation", "business_performance"]
        return [c for c in order if c in fallback]

    def generate_search_query(self, claw_id: str, query: str, history: List[Dict[str, Any]]) -> str:
        """
        Formulates a search query for FAISS based on the active Claw and the user request.
        """
        claw_info = CLAW_METADATA[claw_id]
        system_prompt = f"""You are the Master Orchestrator formulating a semantic search query for the {claw_info['name']}.
Your goal is to write a short, highly targeted search query to find relevant documents, CSV records, guidelines, or logs in the vector database that match the claw's objectives.

Claw Role: {claw_info['role']}
Claw Protocol: {claw_info['protocol']}
User's Overall Query: "{query}"

Respond with ONLY the search query string. Do not use quotes or introductory words. Make it search-engine optimized.
Example response: "Q2 partner transaction ledger CSV columns data"
Search Query:"""
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": system_prompt}],
                temperature=0.1,
                max_tokens=64
            )
            return completion.choices[0].message.content.strip()
        except Exception:
            return query

    def execute_claw(self, claw_id: str, query: str, context: str, shared_state: Dict[str, str]) -> str:
        """
        Executes a single Claw, passing in the user request, FAISS context, and outputs from previous Claws.
        """
        claw_info = CLAW_METADATA[claw_id]
        
        # Format the previous claws outputs for state injection
        state_injection = ""
        if shared_state:
            state_injection = "\n### SHARED STATE (Outputs from previous Claws):\n"
            for prev_id, prev_output in shared_state.items():
                prev_name = CLAW_METADATA[prev_id]["name"]
                state_injection += f"\n--- Start of {prev_name} Output ---\n{prev_output}\n--- End of {prev_name} Output ---\n"

        system_prompt = f"""You are the {claw_info['name']} (Role: {claw_info['role']}).
You are executing your analytical protocol inside a coordinated pipeline.

Your Protocol:
{claw_info['protocol']}

Your Output Structure:
{claw_info['output_structure']}

Guidelines:
1. Ground your analysis strictly in the provided Context.
2. If previous Claws have executed, review their outputs in the SHARED STATE to ensure analytical consistency and build on top of their findings.
3. Maintain a highly professional, objective, numbers-driven, executive-ready tone. Avoid filler words.
4. Output your analysis using markdown. Use markdown tables where requested. Do not include introductory conversational chit-chat (e.g. "Sure, here is the report"). Start directly with your findings or title.
"""

        user_content = f"""Context:
{context}
{state_injection}

User Query / Request:
{query}

Execute analysis and output your structured report:"""

        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.2,
            max_tokens=1024
        )
        return completion.choices[0].message.content.strip()

    def run_pipeline(self, query: str, filter_metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Runs the full orchestrator pipeline: routing, context retrieval, execution, and synthesis.
        """
        # 1. Route query to select Claws
        active_claws = self.route_query(query)
        print(f"Orchestrator routed query to Claws: {active_claws}")

        shared_state = {}
        all_sources = []
        retrieved_contexts = []

        # 2. Sequential execution
        for claw_id in active_claws:
            # Generate claw-specific search query
            search_query = self.generate_search_query(claw_id, query, [])
            print(f"Formulated search query for {claw_id}: '{search_query}'")

            # Search FAISS
            top_chunks = search_faiss(search_query, k=8, filters=filter_metadata)
            
            # Aggregate context and sources
            context_parts = []
            for chunk in top_chunks:
                doc_id = chunk["doc_id"]
                text = chunk["text"]
                metadata = get_document_metadata(doc_id)
                doc_name = metadata.get("name", "Unknown Document") if metadata else "Unknown Document"
                
                context_parts.append(f"Document: {doc_name}\nContent:\n{text}")
                
                # Check for duplicate sources
                if not any(s["doc_id"] == doc_id for s in all_sources):
                    all_sources.append({
                        "doc_id": doc_id,
                        "name": doc_name,
                        "chunk_text": text
                    })

            claw_context = "\n\n---\n\n".join(context_parts) if context_parts else "No relevant documents found in RAG system."
            retrieved_contexts.append(f"--- Context for {CLAW_METADATA[claw_id]['name']} ---\n{claw_context}")

            # Execute Claw
            print(f"Executing {claw_id}...")
            claw_output = self.execute_claw(claw_id, query, claw_context, shared_state)
            shared_state[claw_id] = claw_output

        # 3. Final Synthesis
        # Compile a cohesive report combining the outputs
        report_sections = []
        for claw_id in active_claws:
            claw_name = CLAW_METADATA[claw_id]["name"]
            report_sections.append(f"## {claw_name}\n\n{shared_state[claw_id]}")

        final_report = "\n\n---\n\n".join(report_sections)

        # Synthesize with a final pass if multiple claws ran to ensure a single briefing feel
        if len(active_claws) > 1:
            synthesis_prompt = """You are the Master Orchestrator compiling a unified, executive-ready diagnostic briefing.
You have the outputs of multiple specialized Claws. Your job is to format them into a single, cohesive briefing.

Instructions:
1. Keep the exact calculations, metrics, matrices, and tables generated by each Claw intact.
2. Add a clear, professional header at the top (e.g. "# Executive Diagnostic Briefing").
3. Make sure all sections flow together seamlessly. Maintain clear separation between the Claws using markdown dividers and subheadings.
4. Ensure the style matches a high-end consulting presentation. Use bullet points and clean markdown.
5. If the last claw did not output strategic recommendations or you think it can be improved, feel free to add a clean 3-point recommendation section at the end of the report.

Combine and refine the following report sections:"""

            try:
                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": synthesis_prompt},
                        {"role": "user", "content": final_report}
                    ],
                    temperature=0.1,
                    max_tokens=2048
                )
                final_report = completion.choices[0].message.content.strip()
            except Exception as e:
                print(f"Failed to synthesize final report: {e}")

        # Add mock note if there are no real sources to indicate RAG state
        if not all_sources:
            final_report = (
                "**[Master Orchestrator Notice]** Running in *Simulated Analytics Mode* utilizing contextual mock inputs for partner metrics.\n\n"
                + final_report
            )

        return {
            "answer": final_report,
            "sources": all_sources,
            "active_claws": active_claws
        }
