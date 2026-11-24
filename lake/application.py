import argparse
from dataclasses import asdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from dispatch.readback import initialize_readback, read
from lake.evidence import initialize_evidence, load_round_evidence
from lake.intake import accept_tile
from lake.publish import publish
from lake.receipts import initialize_receipts
from lake.tile_support import initialize_tile_support
from lake.versions import ORIGIN_VERSION, initialize_versions
from rounds.plans import open_round
from rounds.store import initialize_rounds
from surveys.registry import register
from surveys.revisions import RevisionRef, initialize_revisions
from tiles.packets import seal_tile
from tiles.release import release_tile
from tiles.staging import initialize_staging
from workdb import read_database, write_database


EXAMPLES = Path(__file__).resolve().parents[1] / 'examples'


def initialize(lake_path, field_path):
    lake_file, field_file = Path(lake_path).resolve(), Path(field_path).resolve()
    if lake_file == field_file or (lake_file.exists() and field_file.exists() and lake_file.samefile(field_file)):
        raise ValueError('湖库和瓦片工作库须使用不同文件')
    with write_database(field_file, create=True) as field_db:
        initialize_revisions(field_db)
        initialize_staging(field_db)
    with write_database(lake_file, create=True) as lake_db:
        initialize_rounds(lake_db)
        initialize_versions(lake_db)
        initialize_evidence(lake_db)
        initialize_receipts(lake_db)
        initialize_tile_support(lake_db)
        initialize_readback(lake_db)


def run_workday(lake_path, field_path, sources_path, workday_path):
    sources = json.loads(Path(sources_path).read_text(encoding='utf-8'))
    rounds = json.loads(Path(workday_path).read_text(encoding='utf-8'))
    initialize(lake_path, field_path)
    for source in sources:
        register(field_path, **source)

    parent_id = ORIGIN_VERSION
    reports = []
    for work in rounds:
        round_id = work['round_id']
        assignments = {
            tile: tuple(RevisionRef(*ref) for ref in references)
            for tile, references in work['assignments'].items()
        }
        order = work['delivery_order']
        if len(order) != len(assignments) or set(order) != set(assignments):
            raise ValueError('样例送达次序须逐一覆盖改写名单')
        open_round(lake_path, field_path, round_id, parent_id, assignments)
        attempts, clearances = [], []
        with read_database(lake_path) as lake_db:
            prior_evidence = load_round_evidence(lake_db, round_id)
        for tile in order:
            previous = prior_evidence.get(tile)
            packet = previous.packet if previous is not None else seal_tile(lake_path, field_path, round_id, tile)
            receipt = accept_tile(lake_path, round_id, packet)
            clearances.append(asdict(release_tile(lake_path, field_path, packet.source_id, receipt)))
            attempts.append(asdict(publish(lake_path, round_id)))
        if not attempts:
            attempts.append(asdict(publish(lake_path, round_id)))
        version_id = attempts[-1]['version_id']
        if version_id is None:
            raise RuntimeError(f'样例轮次齐件后未签发 {round_id!r}')
        reports.append({
            'round_id': round_id,
            'attempts': attempts,
            'clearances': clearances,
            'dispatch': asdict(read(lake_path, version_id)),
        })
        parent_id = version_id
    return reports


def main(argv=None):
    parser = argparse.ArgumentParser(description='河口巡测湖')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='初始化或重开工作库')
    init.add_argument('lake_path')
    init.add_argument('field_path')
    commands.add_parser('demo', help='运行一天的样例交班')
    args = parser.parse_args(argv)
    if args.command == 'init':
        initialize(args.lake_path, args.field_path)
        return 0
    with TemporaryDirectory(prefix='estuary-workday-') as directory:
        root = Path(directory)
        reports = run_workday(root / 'lake.sqlite', root / 'field.sqlite',
                              EXAMPLES / 'sources.json', EXAMPLES / 'workday.json')
        print(json.dumps(reports, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
