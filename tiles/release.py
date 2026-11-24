from dataclasses import dataclass

from lake.receipts import verify_receipt
from surveys.revisions import require_text
from tiles.staging import clear_staged, load_clearance, load_staged
from workdb import write_database


@dataclass(frozen=True, slots=True)
class ReleaseResult:
    source_id: str
    receipt_id: str
    status: str = 'cleared'


def release_tile(lake_path, field_path, source_id, receipt=None):
    require_text(source_id, '源件号')
    if not verify_receipt(lake_path, receipt) or receipt.source_id != source_id:
        raise ValueError('清理需要该源件的已提交正式收据')
    with write_database(field_path) as field_db:
        clearance = load_clearance(field_db, source_id)
        if clearance is None:
            staged = load_staged(field_db, source_id)
            if staged is None:
                raise LookupError(f'未知暂存源件 {source_id!r}')
            if staged.digest != receipt.packet_digest:
                raise ValueError('收据与暂存封存件不对应')
            clearance = clear_staged(field_db, staged, receipt.receipt_id)
        elif (clearance.digest, clearance.receipt_id) != (receipt.packet_digest, receipt.receipt_id):
            raise ValueError('收据与既有清理结局不对应')
        return ReleaseResult(clearance.source_id, clearance.receipt_id)
