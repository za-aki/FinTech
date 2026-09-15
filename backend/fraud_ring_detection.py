"""
fraud_ring_detection.py

Finds fraud rings using NetworkX graphs. We look for:
1. Merchants sharing the same bank account.
2. Users sharing the same PAN card.
3. Groups of users and merchants disputing a lot of transactions together.

Saves the results to suspicious_cycles.csv so the main pipeline can use it.
"""

import os
import pandas as pd
import numpy as np
import networkx as nx

TXN_PATH = "../data/cleaned/cleaned_transactions.csv"
KYC_PATH = "../data/cleaned/cleaned_kyc.csv"
MER_PATH = "../data/cleaned/cleaned_merchants.csv"
CB_PATH = "../data/cleaned/cleaned_chargebacks.csv"
OUTPUT_CYCLES = "suspicious_cycles.csv"

def run_fraud_ring_detection():
    print("Finding fraud rings using NetworkX...")

    txn = pd.read_csv(TXN_PATH)
    kyc = pd.read_csv(KYC_PATH)
    mer = pd.read_csv(MER_PATH)
    cb = pd.read_csv(CB_PATH)

    rings = []

    # ------------------------------------------------------------
    # 1. MERCHANT SETTLEMENT COLLUSION RINGS
    # Multiple merchant IDs routing revenue to the same bank account
    # ------------------------------------------------------------
    print("\n[1/3] Scanning Merchant Settlement Collusion Rings...")
    shared_acct = mer[mer['settlement_account'].notna()].groupby('settlement_account').agg(
        merchants=('merchant_id', list),
        names=('merchant_name', list),
        count=('merchant_id', 'count')
    ).reset_index()
    collusion_groups = shared_acct[shared_acct['count'] > 1]
    print(f"  ↳ Identified {len(collusion_groups)} merchant collusion clusters sharing settlement accounts.")

    for _, row in collusion_groups.iterrows():
        merch_list = row['merchants']
        # Calculate cluster chargeback exposure
        cluster_txns = txn[txn['merchant_id'].isin(merch_list)]
        total_vol = cluster_txns['amount'].sum()
        failed_count = (cluster_txns['status'] == 'FAILED').sum()
        
        # Risk score proportional to cluster size and failure rate
        score = min(1.0, 0.4 + 0.15 * len(merch_list) + (0.2 if failed_count > 2 else 0.0))
        rings.append({
            "ring_id": f"RING-MERCH-{len(rings)+1:04d}",
            "ring_type": "MERCHANT_SETTLEMENT_COLLUSION",
            "cycle_accounts": " -> ".join(merch_list),
            "entity_count": len(merch_list),
            "composite_score": round(score, 3),
            "cluster_volume": round(total_vol, 2),
            "description": f"Shared bank settlement account {row['settlement_account']} across {len(merch_list)} merchants: {', '.join(str(n) for n in row['names'][:3])}"
        })

    # ------------------------------------------------------------
    # 2. SYNTHETIC IDENTITY & MULE RINGS
    # Multiple user accounts sharing identical government PAN IDs
    # ------------------------------------------------------------
    print("\n[2/3] Scanning Synthetic Identity & Mule Clusters (Shared PAN)...")
    shared_pan = kyc[kyc['pan'].notna()].groupby('pan').agg(
        users=('user_id', list),
        names=('full_name', list),
        count=('user_id', 'count')
    ).reset_index()
    pan_groups = shared_pan[shared_pan['count'] > 1]
    print(f"  ↳ Identified {len(pan_groups)} synthetic identity clusters sharing identical PAN credentials.")

    for _, row in pan_groups.iterrows():
        user_list = row['users']
        user_txns = txn[txn['user_id'].isin(user_list)]
        total_vol = user_txns['amount'].sum()
        
        # Risk score based on shared identity volume
        score = min(0.95, 0.5 + 0.1 * len(user_list))
        rings.append({
            "ring_id": f"RING-SYNTH-{len(rings)+1:04d}",
            "ring_type": "SYNTHETIC_IDENTITY_MULE_RING",
            "cycle_accounts": " -> ".join(user_list),
            "entity_count": len(user_list),
            "composite_score": round(score, 3),
            "cluster_volume": round(total_vol, 2),
            "description": f"Duplicate PAN document shared across {len(user_list)} customer profiles: {', '.join(str(n) for n in row['names'][:3])}"
        })

    # ------------------------------------------------------------
    # 3. COORDINATED DISPUTE BIPARTITE NETWORKS
    # NetworkX graph of users and merchants with high dispute linkages
    # ------------------------------------------------------------
    print("\n[3/3] Building Bipartite Graph for Coordinated Dispute Clusters...")
    disputed_txns = set(cb['txn_id_clean'].dropna())
    disp_df = txn[txn['txn_id'].isin(disputed_txns)]

    G = nx.Graph()
    for _, r in disp_df.iterrows():
        G.add_edge(r['user_id'], r['merchant_id'], amount=r['amount'])

    components = [c for c in nx.connected_components(G) if len(c) >= 4]
    print(f"  ↳ Discovered {len(components)} multi-node coordinated dispute subgraphs.")

    for idx, comp in enumerate(components):
        node_list = list(comp)
        subG = G.subgraph(comp)
        density = nx.density(subG)
        score = min(0.98, 0.6 + 0.3 * density)
        
        rings.append({
            "ring_id": f"RING-DISPUTE-{len(rings)+1:04d}",
            "ring_type": "COORDINATED_DISPUTE_NETWORK",
            "cycle_accounts": " -> ".join(node_list[:8]),
            "entity_count": len(node_list),
            "composite_score": round(score, 3),
            "cluster_volume": round(sum(d['amount'] for _, _, d in subG.edges(data=True)), 2),
            "description": f"Dense dispute cluster of {len(node_list)} interconnected accounts across chargebacks."
        })

    # ------------------------------------------------------------
    # OUTPUT
    # ------------------------------------------------------------
    rings_df = pd.DataFrame(rings)
    rings_df = rings_df.sort_values("composite_score", ascending=False)
    rings_df.to_csv(OUTPUT_CYCLES, index=False)

    print("\n" + "=" * 65)
    print(f"SUCCESS: Generated '{OUTPUT_CYCLES}' with {len(rings_df)} flagged fraud rings.")
    print(f"Top 5 highest risk clusters:\n")
    print(rings_df[['ring_id', 'ring_type', 'entity_count', 'composite_score', 'cluster_volume']].head(5).to_string(index=False))
    print("=" * 65)

if __name__ == "__main__":
    run_fraud_ring_detection()
