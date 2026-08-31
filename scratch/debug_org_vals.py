from core.dynamodb_service import OrganizationsTable
orgs = OrganizationsTable.scan()
for o in orgs:
    oid = o.get('OrgID', '?')
    bp = o.get('BasicPercent', 'MISSING')
    bp_type = type(o.get('BasicPercent')).__name__
    hp = o.get('HRAPercent', 'MISSING')
    hp_type = type(o.get('HRAPercent')).__name__
    pfe = o.get('PFEnabled', 'MISSING')
    pfe_type = type(o.get('PFEnabled')).__name__
    epfp = o.get('EmployeePFPercent', 'MISSING')
    epfp_type = type(o.get('EmployeePFPercent')).__name__
    tdse = o.get('TDSEnabled', 'MISSING')
    tdse_type = type(o.get('TDSEnabled')).__name__
    tsd = o.get('TaxStandardDeduction', 'MISSING')
    tsd_type = type(o.get('TaxStandardDeduction')).__name__
    print(f"OrgID: {oid}")
    print(f"  BasicPercent={bp} ({bp_type})")
    print(f"  HRAPercent={hp} ({hp_type})")
    print(f"  PFEnabled={pfe} ({pfe_type})")
    print(f"  EmployeePFPercent={epfp} ({epfp_type})")
    print(f"  TDSEnabled={tdse} ({tdse_type})")
    print(f"  TaxStandardDeduction={tsd} ({tsd_type})")
    print()
