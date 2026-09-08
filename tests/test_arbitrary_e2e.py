import os
import fitz
import requests

def run_test():
    pdf_path = "test_arbitrary_doc.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Global AI Systems Whitepaper 2026", fontsize=18)
    page.insert_text((50, 90), "Executive Summary:", fontsize=14)
    page.insert_text((50, 120), "In FY26, the company deployed 45,000 autonomous nodes, reaching an accuracy of 98.4%.", fontsize=11)
    page.insert_text((50, 140), "Total operational expenditure was $14.2 million, compared to $9.8 million in FY25.", fontsize=11)
    page.insert_text((50, 160), "System latency decreased to 12.5 ms per inference call across all regional clusters.", fontsize=11)
    page.insert_text((50, 190), "Operational Metrics Overview", fontsize=12)
    page.insert_text((50, 210), "North America: 18,000 nodes, throughput 450 req/s, operational cost $5.2M.", fontsize=10)
    page.insert_text((50, 230), "Europe: 15,000 nodes, throughput 380 req/s, operational cost $4.6M.", fontsize=10)
    page.insert_text((50, 250), "Asia-Pacific: 12,000 nodes, throughput 310 req/s, operational cost $4.4M.", fontsize=10)
    doc.save(pdf_path)
    doc.close()

    print("Created arbitrary PDF:", pdf_path)

    # Create workspace
    resp = requests.post("http://127.0.0.1:8000/api/sessions", json={
        "title": "AI Systems Benchmark",
        "description": "Arbitrary whitepaper analysis"
    })
    assert resp.status_code == 200, resp.text
    session_info = resp.json()
    session_id = session_info["id"]
    print("Created isolated session:", session_id)

    # Upload document
    with open(pdf_path, "rb") as f:
        up_resp = requests.post(f"http://127.0.0.1:8000/api/sessions/{session_id}/documents", files={"file": f})
    assert up_resp.status_code == 200, up_resp.text
    print("Upload succeeded:", up_resp.json())

    # Verify session details & facts
    facts_resp = requests.get(f"http://127.0.0.1:8000/api/sessions/{session_id}/facts")
    facts = facts_resp.json()
    print(f"Extracted {len(facts)} facts from arbitrary document:")
    for f in facts:
        print(f"  - [{f.get('observation_type')}] {f.get('metric_name')}: {f.get('value_raw')} (Page {f.get('page_number')})")

    # Chat query
    chat_resp = requests.post(f"http://127.0.0.1:8000/api/sessions/{session_id}/chat", json={
        "query": "What was the total operational expenditure in FY26 and how many nodes were deployed?"
    })
    chat_data = chat_resp.json()
    print("\nChat Query Response:")
    print("Answer:", chat_data.get("answer"))
    print("Number of citations:", len(chat_data.get("citations", [])))
    for cit in chat_data.get("citations", []):
        print(f"  Citation [Page {cit.get('page_number')}]: {cit.get('quote')}")

    # Clean up test file
    if os.path.exists(pdf_path):
        os.remove(pdf_path)

if __name__ == "__main__":
    run_test()
