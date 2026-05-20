# Supplier Matcher - Deployed Version

## Access
Open the link your admin provided to access the app.

## How to Use

1. **Upload PO file** (Excel or CSV)
   - Must have a column with PO codes/IDs
   - Must have a column with PO descriptions

2. **Upload Supplier file** (Excel or CSV)
   - Must have a column with supplier IDs
   - Must have a column with supplier names

3. **Click RUN MATCHING**
   - Progress updates in real-time
   - Results appear when complete

4. **Download results**
   - CSV or Excel format
   - Timestamped filename

## Data Format

### PO File Example
| Code | Description |
|------|-------------|
| PO001 | Need mining equipment |
| PO002 | Require freight service |

### Supplier File Example
| ID | Name | Services |
|----|------|----------|
| EOI001 | Mining Co | Equipment rental |
| EOI002 | Logistics | Freight shipping |

## Settings

- **Minimum Score**: Adjust to filter results (0-100)
- Lower = more matches
- Higher = stronger matches only

## Processing Time

- Small (10 POs): ~1 minute
- Medium (50 POs): ~5 minutes
- Large (200+ POs): 30+ minutes

Results are available immediately after processing completes.

## Issues?

If upload fails:
- Check file format (Excel .xlsx or CSV)
- Verify columns exist
- Try with smaller file first

Contact your admin for support.
