# -*- coding: utf-8 -*-
"""
Enterprise Domain-Specific Entity Resolver & Authority Linker
Maps Knowledge Graph nodes and academic entities to international authority registers:
- ROR (Research Organization Registry) for academic institutions & publishers (Local + Live ROR REST API)
- Wikidata QIDs & ACM Computing Classification for AI & Engineering (Local + Live Wikidata REST API)
- MeSH (Medical Subject Headings) for clinical & biomedical terms

Confidential & Proprietary - CorpusLD Enterprise Tier
"""

import json
import logging
import re
import urllib.parse
import urllib.request
from functools import lru_cache
from typing import Dict, Any, Optional, List

logger = logging.getLogger("corpusld.enterprise.entity_resolver")

# ----------------------------------------------------------------------
# 1. CURATED HIGH-SPEED LOCAL CANONICAL CACHE (~0ms Latency)
# ----------------------------------------------------------------------
INSTITUTION_ROR_MAP = {
    # Indonesian Top Universities & Research Institutes
    "universitas indonesia": {"name": "Universitas Indonesia", "ror": "https://ror.org/01p2s5n88", "id": "01p2s5n88", "country": "ID"},
    "institut teknologi bandung": {"name": "Institut Teknologi Bandung", "ror": "https://ror.org/04sbc6a41", "id": "04sbc6a41", "country": "ID"},
    "itb": {"name": "Institut Teknologi Bandung", "ror": "https://ror.org/04sbc6a41", "id": "04sbc6a41", "country": "ID"},
    "universitas gadjah mada": {"name": "Universitas Gadjah Mada", "ror": "https://ror.org/03t83re46", "id": "03t83re46", "country": "ID"},
    "ugm": {"name": "Universitas Gadjah Mada", "ror": "https://ror.org/03t83re46", "id": "03t83re46", "country": "ID"},
    "institut teknologi sepuluh nopember": {"name": "Institut Teknologi Sepuluh Nopember", "ror": "https://ror.org/00a7b4455", "id": "00a7b4455", "country": "ID"},
    "its": {"name": "Institut Teknologi Sepuluh Nopember", "ror": "https://ror.org/00a7b4455", "id": "00a7b4455", "country": "ID"},
    "universitas diponegoro": {"name": "Universitas Diponegoro", "ror": "https://ror.org/00b86a877", "id": "00b86a877", "country": "ID"},
    "undip": {"name": "Universitas Diponegoro", "ror": "https://ror.org/00b86a877", "id": "00b86a877", "country": "ID"},
    "universitas airlangga": {"name": "Universitas Airlangga", "ror": "https://ror.org/04nrqd972", "id": "04nrqd972", "country": "ID"},
    "unair": {"name": "Universitas Airlangga", "ror": "https://ror.org/04nrqd972", "id": "04nrqd972", "country": "ID"},
    "institut pertanian bogor": {"name": "IPB University", "ror": "https://ror.org/04tsh1a33", "id": "04tsh1a33", "country": "ID"},
    "ipb": {"name": "IPB University", "ror": "https://ror.org/04tsh1a33", "id": "04tsh1a33", "country": "ID"},
    "ipb university": {"name": "IPB University", "ror": "https://ror.org/04tsh1a33", "id": "04tsh1a33", "country": "ID"},
    "universitas brawijaya": {"name": "Universitas Brawijaya", "ror": "https://ror.org/0126zqb35", "id": "0126zqb35", "country": "ID"},
    "ub": {"name": "Universitas Brawijaya", "ror": "https://ror.org/0126zqb35", "id": "0126zqb35", "country": "ID"},
    "universitas padjadjaran": {"name": "Universitas Padjadjaran", "ror": "https://ror.org/02crv6q28", "id": "02crv6q28", "country": "ID"},
    "unpad": {"name": "Universitas Padjadjaran", "ror": "https://ror.org/02crv6q28", "id": "02crv6q28", "country": "ID"},
    "universitas sebelas maret": {"name": "Universitas Sebelas Maret", "ror": "https://ror.org/01m5gqw36", "id": "01m5gqw36", "country": "ID"},
    "uns": {"name": "Universitas Sebelas Maret", "ror": "https://ror.org/01m5gqw36", "id": "01m5gqw36", "country": "ID"},
    "universitas hasanuddin": {"name": "Universitas Hasanuddin", "ror": "https://ror.org/01m5x5189", "id": "01m5x5189", "country": "ID"},
    "unhas": {"name": "Universitas Hasanuddin", "ror": "https://ror.org/01m5x5189", "id": "01m5x5189", "country": "ID"},
    "universitas sumatera utara": {"name": "Universitas Sumatera Utara", "ror": "https://ror.org/03947b198", "id": "03947b198", "country": "ID"},
    "usu": {"name": "Universitas Sumatera Utara", "ror": "https://ror.org/03947b198", "id": "03947b198", "country": "ID"},
    "universitas tanjungpura": {"name": "Universitas Tanjungpura", "ror": "https://ror.org/03f0b2f63", "id": "03f0b2f63", "country": "ID"},
    "untan": {"name": "Universitas Tanjungpura", "ror": "https://ror.org/03f0b2f63", "id": "03f0b2f63", "country": "ID"},
    "universitas andalas": {"name": "Universitas Andalas", "ror": "https://ror.org/03x3t5924", "id": "03x3t5924", "country": "ID"},
    "unand": {"name": "Universitas Andalas", "ror": "https://ror.org/03x3t5924", "id": "03x3t5924", "country": "ID"},
    "universitas syiah kuala": {"name": "Universitas Syiah Kuala", "ror": "https://ror.org/0286t4f65", "id": "0286t4f65", "country": "ID"},
    "usk": {"name": "Universitas Syiah Kuala", "ror": "https://ror.org/0286t4f65", "id": "0286t4f65", "country": "ID"},
    "unsyiah": {"name": "Universitas Syiah Kuala", "ror": "https://ror.org/0286t4f65", "id": "0286t4f65", "country": "ID"},
    "universitas udayana": {"name": "Universitas Udayana", "ror": "https://ror.org/0014x2067", "id": "0014x2067", "country": "ID"},
    "unud": {"name": "Universitas Udayana", "ror": "https://ror.org/0014x2067", "id": "0014x2067", "country": "ID"},
    "universitas jember": {"name": "Universitas Jember", "ror": "https://ror.org/00z2b8v12", "id": "00z2b8v12", "country": "ID"},
    "unej": {"name": "Universitas Jember", "ror": "https://ror.org/00z2b8v12", "id": "00z2b8v12", "country": "ID"},
    "universitas lampung": {"name": "Universitas Lampung", "ror": "https://ror.org/03c399r89", "id": "03c399r89", "country": "ID"},
    "unila": {"name": "Universitas Lampung", "ror": "https://ror.org/03c399r89", "id": "03c399r89", "country": "ID"},
    "universitas sriwijaya": {"name": "Universitas Sriwijaya", "ror": "https://ror.org/044v2r952", "id": "044v2r952", "country": "ID"},
    "unsri": {"name": "Universitas Sriwijaya", "ror": "https://ror.org/044v2r952", "id": "044v2r952", "country": "ID"},
    "universitas riau": {"name": "Universitas Riau", "ror": "https://ror.org/05c8q3411", "id": "05c8q3411", "country": "ID"},
    "unri": {"name": "Universitas Riau", "ror": "https://ror.org/05c8q3411", "id": "05c8q3411", "country": "ID"},
    "universitas mulawarman": {"name": "Universitas Mulawarman", "ror": "https://ror.org/04k25z018", "id": "04k25z018", "country": "ID"},
    "unmul": {"name": "Universitas Mulawarman", "ror": "https://ror.org/04k25z018", "id": "04k25z018", "country": "ID"},
    "universitas lambung mangkurat": {"name": "Universitas Lambung Mangkurat", "ror": "https://ror.org/0296g5720", "id": "0296g5720", "country": "ID"},
    "ulm": {"name": "Universitas Lambung Mangkurat", "ror": "https://ror.org/0296g5720", "id": "0296g5720", "country": "ID"},
    "universitas sam ratulangi": {"name": "Universitas Sam Ratulangi", "ror": "https://ror.org/013sfx274", "id": "013sfx274", "country": "ID"},
    "unsrat": {"name": "Universitas Sam Ratulangi", "ror": "https://ror.org/013sfx274", "id": "013sfx274", "country": "ID"},
    "universitas negeri yogyakarta": {"name": "Universitas Negeri Yogyakarta", "ror": "https://ror.org/03sp19r91", "id": "03sp19r91", "country": "ID"},
    "uny": {"name": "Universitas Negeri Yogyakarta", "ror": "https://ror.org/03sp19r91", "id": "03sp19r91", "country": "ID"},
    "universitas pendidikan indonesia": {"name": "Universitas Pendidikan Indonesia", "ror": "https://ror.org/02v6h0v47", "id": "02v6h0v47", "country": "ID"},
    "upi": {"name": "Universitas Pendidikan Indonesia", "ror": "https://ror.org/02v6h0v47", "id": "02v6h0v47", "country": "ID"},
    "telkom university": {"name": "Telkom University", "ror": "https://ror.org/03v330230", "id": "03v330230", "country": "ID"},
    "binus university": {"name": "Bina Nusantara University", "ror": "https://ror.org/02m0t9685", "id": "02m0t9685", "country": "ID"},
    "binus": {"name": "Bina Nusantara University", "ror": "https://ror.org/02m0t9685", "id": "02m0t9685", "country": "ID"},
    "badan riset dan inovasi nasional": {"name": "Badan Riset dan Inovasi Nasional", "ror": "https://ror.org/054hwh503", "id": "054hwh503", "country": "ID"},
    "brin": {"name": "Badan Riset dan Inovasi Nasional", "ror": "https://ror.org/054hwh503", "id": "054hwh503", "country": "ID"},

    # Global Tier-1 Academic Institutions
    "massachusetts institute of technology": {"name": "Massachusetts Institute of Technology", "ror": "https://ror.org/0547t3q72", "id": "0547t3q72", "country": "US"},
    "mit": {"name": "Massachusetts Institute of Technology", "ror": "https://ror.org/0547t3q72", "id": "0547t3q72", "country": "US"},
    "stanford university": {"name": "Stanford University", "ror": "https://ror.org/00f54p054", "id": "00f54p054", "country": "US"},
    "harvard university": {"name": "Harvard University", "ror": "https://ror.org/03vek6s52", "id": "03vek6s52", "country": "US"},
    "carnegie mellon university": {"name": "Carnegie Mellon University", "ror": "https://ror.org/05x2bcf33", "id": "05x2bcf33", "country": "US"},
    "cmu": {"name": "Carnegie Mellon University", "ror": "https://ror.org/05x2bcf33", "id": "05x2bcf33", "country": "US"},
    "princeton university": {"name": "Princeton University", "ror": "https://ror.org/00hx57361", "id": "00hx57361", "country": "US"},
    "university of california, berkeley": {"name": "University of California, Berkeley", "ror": "https://ror.org/01an7q238", "id": "01an7q238", "country": "US"},
    "uc berkeley": {"name": "University of California, Berkeley", "ror": "https://ror.org/01an7q238", "id": "01an7q238", "country": "US"},
    "cornell university": {"name": "Cornell University", "ror": "https://ror.org/05bnh6r03", "id": "05bnh6r03", "country": "US"},
    "university of oxford": {"name": "University of Oxford", "ror": "https://ror.org/052gg0110", "id": "052gg0110", "country": "GB"},
    "oxford university": {"name": "University of Oxford", "ror": "https://ror.org/052gg0110", "id": "052gg0110", "country": "GB"},
    "university of cambridge": {"name": "University of Cambridge", "ror": "https://ror.org/013meh722", "id": "013meh722", "country": "GB"},
    "cambridge university": {"name": "University of Cambridge", "ror": "https://ror.org/013meh722", "id": "013meh722", "country": "GB"},
    "eth zurich": {"name": "ETH Zurich", "ror": "https://ror.org/05a28rw58", "id": "05a28rw58", "country": "CH"},
    "national university of singapore": {"name": "National University of Singapore", "ror": "https://ror.org/046rm7j60", "id": "046rm7j60", "country": "SG"},
    "nus": {"name": "National University of Singapore", "ror": "https://ror.org/046rm7j60", "id": "046rm7j60", "country": "SG"},
    "nanyang technological university": {"name": "Nanyang Technological University", "ror": "https://ror.org/02e7zfz27", "id": "02e7zfz27", "country": "SG"},
    "ntu": {"name": "Nanyang Technological University", "ror": "https://ror.org/02e7zfz27", "id": "02e7zfz27", "country": "SG"},
    "tsinghua university": {"name": "Tsinghua University", "ror": "https://ror.org/03cve4549", "id": "03cve4549", "country": "CN"},
    "peking university": {"name": "Peking University", "ror": "https://ror.org/02v51f717", "id": "02v51f717", "country": "CN"},
    "university of tokyo": {"name": "The University of Tokyo", "ror": "https://ror.org/057zh3y96", "id": "057zh3y96", "country": "JP"},

    # Global Scientific Publishers & Societies
    "elsevier": {"name": "Elsevier", "ror": "https://ror.org/01ggx4157", "id": "01ggx4157", "country": "NL"},
    "springer nature": {"name": "Springer Nature", "ror": "https://ror.org/05697k177", "id": "05697k177", "country": "DE"},
    "ieee": {"name": "Institute of Electrical and Electronics Engineers", "ror": "https://ror.org/01k5qnb77", "id": "01k5qnb77", "country": "US"},
    "acm": {"name": "Association for Computing Machinery", "ror": "https://ror.org/02d2k5257", "id": "02d2k5257", "country": "US"},
    "wiley": {"name": "Wiley", "ror": "https://ror.org/01t87vg90", "id": "01t87vg90", "country": "US"},
    "nature publishing group": {"name": "Nature Portfolio", "ror": "https://ror.org/02b55f691", "id": "02b55f691", "country": "GB"},
    "w3c": {"name": "World Wide Web Consortium", "ror": "https://ror.org/02b55f691", "id": "02b55f691", "country": "US"},
    "crossref": {"name": "Crossref", "ror": "https://ror.org/02t43z281", "id": "02t43z281", "country": "US"},
    "orcid": {"name": "ORCID", "ror": "https://ror.org/047f03g78", "id": "047f03g78", "country": "US"},
}

# Authority Knowledge Concepts Map (Wikidata / MeSH / ACM)
SCIENTIFIC_CONCEPT_AUTHORITY_MAP = {
    # Machine Learning, Semantic Web & AI
    "knowledge graph": {"wikidata": "https://www.wikidata.org/wiki/Q33002955", "domain": "Computer Science"},
    "linked data": {"wikidata": "https://www.wikidata.org/wiki/Q515701", "domain": "Computer Science"},
    "semantic web": {"wikidata": "https://www.wikidata.org/wiki/Q54837", "domain": "Computer Science"},
    "schema.org": {"wikidata": "https://www.wikidata.org/wiki/Q3475355", "domain": "Computer Science"},
    "retrieval-augmented generation": {"wikidata": "https://www.wikidata.org/wiki/Q123565622", "domain": "Computer Science"},
    "rag": {"wikidata": "https://www.wikidata.org/wiki/Q123565622", "domain": "Computer Science"},
    "ontology": {"wikidata": "https://www.wikidata.org/wiki/Q324254", "domain": "Computer Science"},
    "json-ld": {"wikidata": "https://www.wikidata.org/wiki/Q6109033", "domain": "Computer Science"},
    "rdf": {"wikidata": "https://www.wikidata.org/wiki/Q54872", "domain": "Computer Science"},
    "machine learning": {"wikidata": "https://www.wikidata.org/wiki/Q2539", "domain": "Computer Science"},
    "deep learning": {"wikidata": "https://www.wikidata.org/wiki/Q197536", "domain": "Computer Science"},
    "neural network": {"wikidata": "https://www.wikidata.org/wiki/Q192776", "domain": "Computer Science"},
    "convolutional neural network": {"wikidata": "https://www.wikidata.org/wiki/Q13129841", "domain": "Computer Science"},
    "cnn": {"wikidata": "https://www.wikidata.org/wiki/Q13129841", "domain": "Computer Science"},
    "transformer": {"wikidata": "https://www.wikidata.org/wiki/Q85810444", "domain": "Computer Science"},
    "state space model": {"wikidata": "https://www.wikidata.org/wiki/Q108251548", "domain": "Computer Science"},
    "mamba": {"wikidata": "https://www.wikidata.org/wiki/Q108251548", "domain": "Computer Science"},
    "reinforcement learning": {"wikidata": "https://www.wikidata.org/wiki/Q830687", "domain": "Computer Science"},
    "support vector machine": {"wikidata": "https://www.wikidata.org/wiki/Q328709", "domain": "Computer Science"},
    "svm": {"wikidata": "https://www.wikidata.org/wiki/Q328709", "domain": "Computer Science"},
    "large language model": {"wikidata": "https://www.wikidata.org/wiki/Q115305900", "domain": "Computer Science"},
    "llm": {"wikidata": "https://www.wikidata.org/wiki/Q115305900", "domain": "Computer Science"},
    "internet of things": {"wikidata": "https://www.wikidata.org/wiki/Q251649", "domain": "Computer Science"},
    "iot": {"wikidata": "https://www.wikidata.org/wiki/Q251649", "domain": "Computer Science"},
    "graph neural network": {"wikidata": "https://www.wikidata.org/wiki/Q97358752", "domain": "Computer Science"},
    "natural language processing": {"wikidata": "https://www.wikidata.org/wiki/Q30642", "domain": "Computer Science"},
    "nlp": {"wikidata": "https://www.wikidata.org/wiki/Q30642", "domain": "Computer Science"},
    "vector database": {"wikidata": "https://www.wikidata.org/wiki/Q117749453", "domain": "Computer Science"},
    "qdrant": {"wikidata": "https://www.wikidata.org/wiki/Q117749453", "domain": "Computer Science"},

    # Formal Verification & Systems
    "formal verification": {"wikidata": "https://www.wikidata.org/wiki/Q782977", "domain": "Computer Science"},
    "model checking": {"wikidata": "https://www.wikidata.org/wiki/Q1142517", "domain": "Computer Science"},
    "smt solver": {"wikidata": "https://www.wikidata.org/wiki/Q7394627", "domain": "Computer Science"},
    "bounded model checking": {"wikidata": "https://www.wikidata.org/wiki/Q4949980", "domain": "Computer Science"},
    "esbmc": {"wikidata": "https://www.wikidata.org/wiki/Q782977", "domain": "Computer Science"},
    "microcontroller": {"wikidata": "https://www.wikidata.org/wiki/Q165668", "domain": "Electrical Engineering"},
    "arduino": {"wikidata": "https://www.wikidata.org/wiki/Q175925", "domain": "Electrical Engineering"},
    "esp32": {"wikidata": "https://www.wikidata.org/wiki/Q27044455", "domain": "Electrical Engineering"},
    "lorawan": {"wikidata": "https://www.wikidata.org/wiki/Q25052959", "domain": "Telecommunications"},

    # Biomedical & Health Sciences
    "diabetes mellitus": {"mesh": "https://meshb.nlm.nih.gov/record/ui?ui=D003920", "wikidata": "https://www.wikidata.org/wiki/Q12206", "domain": "Medicine"},
    "hypertension": {"mesh": "https://meshb.nlm.nih.gov/record/ui?ui=D006973", "wikidata": "https://www.wikidata.org/wiki/Q110786", "domain": "Medicine"},
    "polymerase chain reaction": {"mesh": "https://meshb.nlm.nih.gov/record/ui?ui=D016133", "wikidata": "https://www.wikidata.org/wiki/Q176996", "domain": "Biochemistry"},
    "pcr": {"mesh": "https://meshb.nlm.nih.gov/record/ui?ui=D016133", "wikidata": "https://www.wikidata.org/wiki/Q176996", "domain": "Biochemistry"},
    "covid-19": {"mesh": "https://meshb.nlm.nih.gov/record/ui?ui=D000086382", "wikidata": "https://www.wikidata.org/wiki/Q84263196", "domain": "Medicine"},
    "crispr": {"mesh": "https://meshb.nlm.nih.gov/record/ui?ui=D000078385", "wikidata": "https://www.wikidata.org/wiki/Q15086884", "domain": "Genetics"},
    "myocardial infarction": {"mesh": "https://meshb.nlm.nih.gov/record/ui?ui=D009203", "wikidata": "https://www.wikidata.org/wiki/Q12152", "domain": "Cardiology"},

    # Energy, Chemical, Material & Environment
    "battery energy storage system": {"wikidata": "https://www.wikidata.org/wiki/Q810931", "domain": "Energy Engineering"},
    "bess": {"wikidata": "https://www.wikidata.org/wiki/Q810931", "domain": "Energy Engineering"},
    "photovoltaic": {"wikidata": "https://www.wikidata.org/wiki/Q193135", "domain": "Energy"},
    "solar cell": {"wikidata": "https://www.wikidata.org/wiki/Q48299", "domain": "Energy"},
    "greenhouse gas": {"wikidata": "https://www.wikidata.org/wiki/Q167336", "domain": "Environmental Science"},
    "fuel cell": {"wikidata": "https://www.wikidata.org/wiki/Q180253", "domain": "Energy"},
    "renewable energy": {"wikidata": "https://www.wikidata.org/wiki/Q12705", "domain": "Environmental Science"},
    "peatland": {"wikidata": "https://www.wikidata.org/wiki/Q1056754", "domain": "Earth Science"},
    "peat soil": {"wikidata": "https://www.wikidata.org/wiki/Q18481", "domain": "Earth Science"},
    "e-methanol": {"wikidata": "https://www.wikidata.org/wiki/Q14982", "domain": "Chemical Engineering"},
    "methanol synthesis": {"wikidata": "https://www.wikidata.org/wiki/Q14982", "domain": "Chemical Engineering"},
    "carbon capture and storage": {"wikidata": "https://www.wikidata.org/wiki/Q836371", "domain": "Environmental Science"},
    "pyrolysis": {"wikidata": "https://www.wikidata.org/wiki/Q181938", "domain": "Chemical Engineering"},
    "electrolysis": {"wikidata": "https://www.wikidata.org/wiki/Q131362", "domain": "Chemistry"},
    "biomass": {"wikidata": "https://www.wikidata.org/wiki/Q18848", "domain": "Energy"},
}

USER_AGENT = "CorpusLD/3.0 (Enterprise Academic Entity Authority Linker; mailto:sharrifff880@gmail.com; https://sharriffajar.pages.dev)"


# ----------------------------------------------------------------------
# 2. LIVE ROR REST REGISTRY LOOKUP ENGINE
# ----------------------------------------------------------------------
@lru_cache(maxsize=512)
def lookup_ror_live(query_text: str) -> Optional[Dict[str, Any]]:
    """
    Queries official ROR API (https://api.ror.org/v2/organizations) to dynamically
    resolve any global research institution, university, lab, or publisher.
    """
    if not query_text or len(query_text.strip()) < 3:
        return None

    # Clean affiliation noise (e.g. "Dept of Computer Science, Princeton University" -> "Princeton University")
    clean_query = query_text.strip()
    parts = [p.strip() for p in clean_query.split(',') if p.strip()]
    cand_query = parts[-1] if len(parts) > 1 and any(w in parts[-1].lower() for w in ["universit", "institut", "college", "school", "center", "centre", "academy"]) else clean_query

    url = f"https://api.ror.org/v2/organizations?query={urllib.parse.quote_plus(cand_query)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=4) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                items = data.get("items", [])
                if items:
                    top = items[0]
                    ror_id = top.get("id")
                    names = top.get("names", [{}])
                    official_name = names[0].get("value") if names else cand_query
                    locations = top.get("locations", [{}])
                    country_code = locations[0].get("geonames_details", {}).get("country_code", "") if locations else ""
                    return {
                        "name": official_name,
                        "ror": ror_id,
                        "id": ror_id.replace("https://ror.org/", "") if ror_id else "",
                        "country": country_code,
                        "source": "live_ror_registry"
                    }
    except Exception as e:
        logger.debug("Live ROR lookup error for '%s': %s", cand_query, e)

    return None


# ----------------------------------------------------------------------
# 3. LIVE WIKIDATA CONCEPT SEARCH ENGINE
# ----------------------------------------------------------------------
@lru_cache(maxsize=512)
def lookup_wikidata_concept_live(concept_name: str) -> Optional[Dict[str, Any]]:
    """
    Queries official Wikidata Search API to dynamically resolve any scientific concept,
    algorithm, methodology, or technology term to its canonical QID URI.
    """
    if not concept_name or len(concept_name.strip()) < 3:
        return None

    clean_name = concept_name.strip()
    url = f"https://www.wikidata.org/w/api.php?action=wbsearchentities&search={urllib.parse.quote_plus(clean_name)}&language=en&format=json&limit=1"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=4) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                search_results = data.get("search", [])
                if search_results:
                    top = search_results[0]
                    concept_uri = top.get("concepturi")
                    desc = top.get("description", "")
                    label = top.get("label", clean_name)
                    if concept_uri:
                        return {
                            "wikidata": concept_uri,
                            "label": label,
                            "description": desc,
                            "domain": "Interdisciplinary Science",
                            "source": "live_wikidata_registry"
                        }
    except Exception as e:
        logger.debug("Live Wikidata lookup error for '%s': %s", clean_name, e)

    return None


# ----------------------------------------------------------------------
# 4. HYBRID RESOLVER ROUTERS
# ----------------------------------------------------------------------
def resolve_academic_institution(text: str) -> Optional[Dict[str, Any]]:
    """
    Resolves institutional affiliation text to canonical ROR identity
    using Fast Local Canonical Cache with Dynamic Live ROR fallback.
    """
    if not text:
        return None
    clean_text = text.lower().strip()

    # 1. Fast Cache Scan (~0ms)
    for pattern, info in INSTITUTION_ROR_MAP.items():
        if re.search(r'\b' + re.escape(pattern) + r'\b', clean_text):
            return info

    # 2. Dynamic Live ROR Lookup
    return lookup_ror_live(text)


def resolve_scientific_concept_authority(concept_name: str) -> Optional[Dict[str, Any]]:
    """
    Resolves concept name to MeSH / Wikidata authority URI
    using Fast Local Ontology Cache with Dynamic Live Wikidata fallback.
    """
    if not concept_name:
        return None
    clean_name = concept_name.lower().strip()

    # 1. Fast Cache Exact & Substring Scan
    if clean_name in SCIENTIFIC_CONCEPT_AUTHORITY_MAP:
        return SCIENTIFIC_CONCEPT_AUTHORITY_MAP[clean_name]

    for pattern, info in SCIENTIFIC_CONCEPT_AUTHORITY_MAP.items():
        if re.search(r'\b' + re.escape(pattern) + r'\b', clean_name):
            return info

    # 2. Dynamic Live Wikidata Registry Lookup
    return lookup_wikidata_concept_live(concept_name)


def enrich_knowledge_graph_with_authorities(kg_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enriches Knowledge Graph nodes with Schema.org sameAs authority URIs
    (Wikidata, MeSH, ROR) for enterprise discoverability and graph linking.
    """
    enriched = []
    for node in kg_nodes:
        n_copy = dict(node)
        label = n_copy.get("name") or n_copy.get("label") or ""
        ntype = n_copy.get("node_type") or n_copy.get("type") or ""

        raw_same = n_copy.get("sameAs") or n_copy.get("same_as") or []
        if isinstance(raw_same, str):
            same_as_links = [raw_same.strip()] if raw_same.strip() else []
        elif isinstance(raw_same, list):
            same_as_links = [str(x).strip() for x in raw_same if str(x).strip()]
        else:
            same_as_links = []

        if "Organization" in ntype or any(w in label.lower() for w in ["universit", "institut", "lab", "college", "school", "center", "academy", "brin"]):
            inst_info = resolve_academic_institution(label)
            if inst_info and inst_info.get("ror") and inst_info["ror"] not in same_as_links:
                same_as_links.append(inst_info["ror"])
                n_copy.setdefault("properties", {})["ror_id"] = inst_info.get("id", "")
                n_copy.setdefault("properties", {})["canonical_name"] = inst_info.get("name", label)

        concept_info = resolve_scientific_concept_authority(label)
        if concept_info:
            if concept_info.get("wikidata") and concept_info["wikidata"] not in same_as_links:
                same_as_links.append(concept_info["wikidata"])
            if concept_info.get("mesh") and concept_info["mesh"] not in same_as_links:
                same_as_links.append(concept_info["mesh"])
            if concept_info.get("domain"):
                n_copy.setdefault("properties", {})["scientific_domain"] = concept_info.get("domain")

        if same_as_links:
            n_copy["sameAs"] = same_as_links

        enriched.append(n_copy)
    return enriched

