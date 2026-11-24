from fractions import Fraction
from pathlib import Path

from dispatch.routes import HandoverPolicy, Route, plan_route, route_plan_record
from lake.intake import accept_tile
from lake.publish import publish
from surveys.registry import register
from tests.fixtures import Workspace


def fx(value):
    return Fraction(value)


class RouteWorkspace(Workspace):
    def publish_round(self, round_id, parent_id, assignments):
        self.plan(round_id, parent_id, assignments)
        for tile in assignments:
            accept_tile(self.lake, round_id, self.seal(round_id, tile))
        result = publish(self.lake, round_id)
        self.assertEqual(result.status, 'published')
        return result.version_id


class RouteTests(RouteWorkspace):
    def test_geometry_covered_but_no_direct_handover(self):
        zone = self.revision('zone', 'Z', 'r1', [0, 0, 30, 10])
        # Two crews whose coverage only touches at x=10: full geometric cover,
        # but no common stretch, so no handover is allowed.
        alpha = self.revision('footprint', 'ALPHA', 'r1', [0, 4, 10, 6], crew='alpha')
        beta = self.revision('footprint', 'BETA', 'r1', [10, 4, 30, 6], crew='beta')
        version = self.publish_round('direct', 'origin', {
            '0,0': (zone, alpha),
            '1,0': (zone, alpha, beta),
            '2,0': (zone, beta),
        })
        route = Route(((0, 5), (30, 5)), 'Z')
        plan = plan_route(self.lake, version, route, HandoverPolicy(('alpha', 'beta'), 3, fx(2)))
        self.assertEqual(plan.reachable, fx(10))
        self.assertEqual(plan.handover_count, 0)
        self.assertFalse(plan.completed)

    def test_intermediate_crew_extends_reach(self):
        zone = self.revision('zone', 'Z', 'r1', [0, 0, 30, 10])
        alpha = self.revision('footprint', 'ALPHA', 'r1', [0, 4, 10, 6], crew='alpha')
        beta = self.revision('footprint', 'BETA', 'r1', [10, 4, 30, 6], crew='beta')
        gamma = self.revision('footprint', 'GAMMA', 'r1', [5, 4, 25, 6], crew='gamma')
        version = self.publish_round('bridge', 'origin', {
            '0,0': (zone, alpha, gamma),
            '1,0': (zone, alpha, beta, gamma),
            '2,0': (zone, beta, gamma),
        })
        route = Route(((0, 5), (30, 5)), 'Z')
        plan = plan_route(self.lake, version, route,
                          HandoverPolicy(('alpha', 'beta', 'gamma'), 3, fx(2)))
        self.assertEqual(plan.reachable, fx(30))
        self.assertTrue(plan.completed)
        self.assertEqual(plan.handover_count, 2)
        self.assertEqual([(h.outgoing, h.incoming, h.position) for h in plan.handovers],
                         [('alpha', 'gamma', fx(7)), ('gamma', 'beta', fx(12))])
        self.assertEqual([(s.crew, s.start, s.end) for s in plan.segments],
                         [('alpha', fx(0), fx(7)), ('gamma', fx(7), fx(12)),
                          ('beta', fx(12), fx(30))])

    def test_zero_outside_zone_stops_at_boundary(self):
        zone = self.revision('zone', 'Z', 'r1', [0, 0, 12, 10])
        alpha = self.revision('footprint', 'ALPHA', 'r1', [0, 4, 30, 6], crew='alpha')
        version = self.publish_round('zone', 'origin', {
            '0,0': (zone, alpha), '1,0': (zone, alpha), '2,0': (zone, alpha),
        })
        route = Route(((0, 5), (30, 5)), 'Z')
        plan = plan_route(self.lake, version, route, HandoverPolicy(('alpha',), 0, fx(2)))
        self.assertEqual(plan.reachable, fx(12))

    def test_fewest_handovers_breaks_ties(self):
        zone = self.revision('zone', 'Z', 'r1', [0, 0, 20, 10])
        alpha = self.revision('footprint', 'ALPHA', 'r1', [0, 4, 20, 6], crew='alpha')
        beta = self.revision('footprint', 'BETA', 'r1', [0, 3, 20, 5], crew='beta')
        version = self.publish_round('tie', 'origin', {
            '0,0': (zone, alpha, beta), '1,0': (zone, alpha, beta),
        })
        route = Route(((0, 4.5), (20, 4.5)), 'Z')
        plan = plan_route(self.lake, version, route, HandoverPolicy(('alpha', 'beta'), 2, fx(2)))
        self.assertEqual(plan.reachable, fx(20))
        self.assertEqual(plan.handover_count, 0)
        self.assertEqual([s.crew for s in plan.segments], ['alpha'])

    def test_no_crew_covers_start(self):
        zone = self.revision('zone', 'Z', 'r1', [0, 0, 20, 10])
        alpha = self.revision('footprint', 'ALPHA', 'r1', [5, 4, 20, 6], crew='alpha')
        version = self.publish_round('late', 'origin', {
            '0,0': (zone, alpha), '1,0': (zone, alpha),
        })
        route = Route(((0, 5), (20, 5)), 'Z')
        plan = plan_route(self.lake, version, route, HandoverPolicy(('alpha',), 0, fx(2)))
        self.assertEqual(plan.reachable, fx(0))
        self.assertEqual(plan.segments, ())

    def test_unknown_version(self):
        route = Route(((0, 5), (10, 5)), 'Z')
        with self.assertRaises(LookupError):
            plan_route(self.lake, 'lake-missing', route, HandoverPolicy(('alpha',), 0, fx(1)))

    def test_handover_budget_limits_reach(self):
        zone = self.revision('zone', 'Z', 'r1', [0, 0, 30, 10])
        alpha = self.revision('footprint', 'ALPHA', 'r1', [0, 4, 10, 6], crew='alpha')
        beta = self.revision('footprint', 'BETA', 'r1', [10, 4, 30, 6], crew='beta')
        gamma = self.revision('footprint', 'GAMMA', 'r1', [5, 4, 25, 6], crew='gamma')
        version = self.publish_round('budget', 'origin', {
            '0,0': (zone, alpha, gamma),
            '1,0': (zone, alpha, beta, gamma),
            '2,0': (zone, beta, gamma),
        })
        route = Route(((0, 5), (30, 5)), 'Z')
        zero = plan_route(self.lake, version, route, HandoverPolicy(('alpha', 'beta', 'gamma'), 0, fx(2)))
        self.assertEqual(zero.reachable, fx(10))
        one = plan_route(self.lake, version, route, HandoverPolicy(('alpha', 'beta', 'gamma'), 1, fx(2)))
        # With one handover alpha can reach gamma (common 5..10) and gamma runs to 25.
        self.assertEqual(one.reachable, fx(25))
        self.assertEqual(one.handover_count, 1)
        two = plan_route(self.lake, version, route, HandoverPolicy(('alpha', 'beta', 'gamma'), 2, fx(2)))
        self.assertEqual(two.reachable, fx(30))
        self.assertEqual(two.handover_count, 2)

    def test_version_isolation_and_carried_forward_coverage(self):
        zone = self.revision('zone', 'Z', 'r1', [0, 0, 20, 10])
        alpha = self.revision('footprint', 'ALPHA', 'r1', [0, 4, 20, 6], crew='alpha')
        beta = self.revision('footprint', 'BETA', 'r1', [10, 4, 20, 6], crew='beta')
        first = self.publish_round('first', 'origin', {
            '0,0': (zone, alpha), '1,0': (zone, alpha),
        })
        # Only the east tile changes; the west tile keeps alpha's accepted coverage.
        second = self.publish_round('second', first, {'1,0': (zone, beta)})
        route = Route(((0, 5), (20, 5)), 'Z')
        old = plan_route(self.lake, first, route, HandoverPolicy(('alpha', 'beta'), 1, fx(1)))
        new = plan_route(self.lake, second, route, HandoverPolicy(('alpha', 'beta'), 1, fx(1)))
        self.assertEqual([s.crew for s in old.segments], ['alpha'])
        self.assertEqual(old.reachable, fx(20))
        # West alpha still covers 0..10 from the accepted parent support; east beta
        # starts at 10, so the two only touch and cannot hand over.
        self.assertEqual([s.crew for s in new.segments], ['alpha'])
        self.assertEqual(new.reachable, fx(10))
        self.assertEqual(new.handover_count, 0)

    def test_diagonal_route_handover(self):
        zone = self.revision('zone', 'Z', 'r1', [0, 0, 20, 20])
        beta = self.revision('footprint', 'BETA', 'r1', [0, 0, 20, 20], crew='beta')
        version = self.publish_round('diag', 'origin', {
            '0,0': (zone, beta), '1,0': (zone, beta),
            '0,1': (zone, beta), '1,1': (zone, beta),
        })
        route = Route(((0, 0), (20, 20)), 'Z')
        plan = plan_route(self.lake, version, route, HandoverPolicy(('beta',), 0, fx(1)))
        self.assertTrue(plan.completed)
        self.assertAlmostEqual(float(plan.reachable), 20 * 2 ** 0.5, places=6)

    def test_invalid_route_arguments(self):
        with self.assertRaises(ValueError):
            Route(((0, 0),), 'Z')
        with self.assertRaises(ValueError):
            Route(((0, 0), (1, 1)), '')
        with self.assertRaises(ValueError):
            HandoverPolicy((), 0, fx(1))
        with self.assertRaises(ValueError):
            HandoverPolicy(('a', 'a'), 0, fx(1))
        with self.assertRaises(ValueError):
            HandoverPolicy(('a',), -1, fx(1))
        with self.assertRaises(ValueError):
            HandoverPolicy(('a',), 0, fx(0))

    def test_check_survives_source_database_removal(self):
        zone = self.revision('zone', 'Z', 'r1', [0, 0, 30, 10])
        alpha = self.revision('footprint', 'ALPHA', 'r1', [0, 4, 10, 6], crew='alpha')
        beta = self.revision('footprint', 'BETA', 'r1', [10, 4, 30, 6], crew='beta')
        gamma = self.revision('footprint', 'GAMMA', 'r1', [5, 4, 25, 6], crew='gamma')
        version = self.publish_round('closed', 'origin', {
            '0,0': (zone, alpha, gamma),
            '1,0': (zone, alpha, beta, gamma),
            '2,0': (zone, beta, gamma),
        })
        before = plan_route(self.lake, version, Route(((0, 5), (30, 5)), 'Z'),
                            HandoverPolicy(('alpha', 'beta', 'gamma'), 2, fx(2)))
        Path(self.field).unlink()
        after = plan_route(self.lake, version, Route(((0, 5), (30, 5)), 'Z'),
                           HandoverPolicy(('alpha', 'beta', 'gamma'), 2, fx(2)))
        self.assertEqual(after, before)
        self.assertEqual(after.reachable, fx(30))

    def test_crew_change_only_affects_new_version(self):
        zone = self.revision('zone', 'Z', 'r1', [0, 0, 20, 10])
        alpha = self.revision('footprint', 'ALPHA', 'r1', [0, 4, 20, 6], crew='alpha')
        original = register(self.field, 'footprint', 'ALPHA', 'r1',
                            '外业 ALPHA r1', [0, 4, 20, 6], crew='alpha')
        with self.assertRaisesRegex(ValueError, '冲突'):
            self.revision('footprint', 'ALPHA', 'r1', [0, 4, 20, 6], crew='beta')
        first = self.publish_round('old', 'origin', {'0,0': (zone, alpha)})
        beta = self.revision('footprint', 'ALPHA', 'r2', [0, 4, 20, 6], crew='beta')
        second = self.publish_round('new', first, {'0,0': (zone, beta)})
        route = Route(((0, 5), (20, 5)), 'Z')
        old_plan = plan_route(self.lake, first, route, HandoverPolicy(('alpha', 'beta'), 0, fx(1)))
        new_plan = plan_route(self.lake, second, route, HandoverPolicy(('alpha', 'beta'), 0, fx(1)))
        self.assertEqual([s.crew for s in old_plan.segments], ['alpha'])
        self.assertEqual([s.crew for s in new_plan.segments], ['beta'])
        self.assertEqual(original.crew, 'alpha')

    def test_plan_record_is_serializable(self):
        zone = self.revision('zone', 'Z', 'r1', [0, 0, 20, 10])
        alpha = self.revision('footprint', 'ALPHA', 'r1', [0, 4, 14, 6], crew='alpha')
        beta = self.revision('footprint', 'BETA', 'r1', [10, 4, 20, 6], crew='beta')
        version = self.publish_round('record', 'origin', {
            '0,0': (zone, alpha, beta), '1,0': (zone, alpha, beta),
        })
        plan = plan_route(self.lake, version, Route(((0, 5), (20, 5)), 'Z'),
                          HandoverPolicy(('alpha', 'beta'), 1, fx(2)))
        record = route_plan_record(plan)
        self.assertEqual((record['reachable'], record['route_length']), ('20', '20'))
        self.assertEqual(record['handover_count'], 1)
        self.assertEqual(record['handovers'][0]['outgoing'], 'alpha')
        self.assertEqual(record['handovers'][0]['incoming'], 'beta')
        self.assertEqual(record['handovers'][0]['common_length'], '2')
        self.assertTrue(record['segments'][0]['strips'])
        self.assertEqual(record['segments'][0]['strips'][0]['tile_id'], '0,0')


