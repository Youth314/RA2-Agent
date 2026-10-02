"""Fixed Stop faults for isolated DLL verification, never a model capability."""
from ra2agent.constants import NS, UnitAction
from ra2agent.engine import payloads
from ra2agent.engine.proto import fmap, pb_bytes, pb_uint

FAULT_ERRORS = {
    'wrong_native_id': 'controlled actor absent, changed or unsupported',
    'wrong_house': 'controlled player context changed',
    'stale_basis': 'controlled basis frame is stale',
    'future_basis': 'controlled basis frame is stale',
    'empty_actors': 'controlled order requires one actor, native ID and house',
    'multiple_actors': 'controlled order requires one actor, native ID and house',
    'missing_native_id': 'controlled order requires one actor, native ID and house',
    'missing_house': 'controlled order requires one actor, native ID and house',
    'coordinates': 'stop does not accept a target',
    'object_target': 'stop does not accept a target',
    'foreign_actor': 'controlled actor absent, changed or unsupported',
    'infantry_actor': 'controlled actor absent, changed or unsupported',
}


def fault_request(body, fault, *, other_house=None, foreign_pointer=None,
                  foreign_native_id=None, infantry_pointer=None, infantry_native_id=None):
    if fault not in FAULT_ERRORS:
        raise ValueError('Unknown fixed Stop fault')
    fields = fmap(body)
    if (set(fields) != {1, 2, 5, 6, 7}
            or any(len(v) != 1 or v[0][0] != 0 for v in fields.values())
            or fields[2][0][1] != UnitAction.PLAYER_STOP):
        raise ValueError('Expected a single controlled Stop baseline')
    values = {n: v[0][1] for n, v in fields.items()}
    extra = b''

    def positive(value):
        if type(value) is not int or not 0 < value <= 0xFFFFFFFF:
            raise ValueError('Missing uint32 fixture identity')
        return value

    for n in (1, 5, 6):
        positive(values[n])
    if not 0 <= values[7] <= 0xFFFFFFFF:
        raise ValueError('Invalid basis frame')
    if fault == 'wrong_native_id':
        values[5] = values[5] % 0xFFFFFFFF + 1
    elif fault == 'wrong_house':
        values[6] = positive(other_house)
        if values[6] == fields[6][0][1]:
            raise ValueError('Fixture house must differ')
    elif fault == 'stale_basis':
        if values[7] <= 150:
            raise ValueError('Need advancing frame > 150')
        values[7] = 0
    elif fault == 'future_basis':
        if values[7] > 0xFFFFFFFF - 100000:
            raise ValueError('Future frame overflow')
        values[7] += 100000
    elif fault == 'empty_actors':
        del values[1]
    elif fault == 'multiple_actors':
        extra = pb_uint(1, values[1])
    elif fault == 'missing_native_id':
        del values[5]
    elif fault == 'missing_house':
        del values[6]
    elif fault == 'coordinates':
        extra = pb_bytes(4, b'')  # even an explicitly present zero cell is forbidden
    elif fault == 'object_target':
        extra = pb_uint(3, values[1])
    elif fault == 'foreign_actor':
        values[1], values[5] = positive(foreign_pointer), positive(foreign_native_id)
        if values[1] == fields[1][0][1]:
            raise ValueError('Fixture actor must differ')
    elif fault == 'infantry_actor':
        values[1], values[5] = positive(infantry_pointer), positive(infantry_native_id)
        if values[1] == fields[1][0][1]:
            raise ValueError('Fixture actor must differ')
    return b''.join(pb_uint(n, v) for n, v in sorted(values.items())) + extra


class StopFaultTransport:
    def __init__(self, client):
        self.client = client
        self.armed = None
        self.requests = []
        self.results = []

    def __getattr__(self, name):
        return getattr(self.client, name)

    def arm(self, fault, **identities):
        if fault not in FAULT_ERRORS or self.armed is not None:
            raise ValueError('Invalid or already armed fault')
        self.armed = fault, identities

    def stop_order(self, pointer, native_id, house_pointer, basis_frame):
        original = payloads.stop_order(pointer, native_id, house_pointer, basis_frame)
        armed, self.armed = self.armed, None
        body = fault_request(original, armed[0], **armed[1]) if armed else original
        self.requests.append({'fault': armed[0] if armed else None,
                              'valid_request_hex': original.hex(), 'request_hex': body.hex()})
        result = (self.client.send_command(NS + 'UnitOrder', body) if armed else
                  self.client.stop_order(pointer, native_id, house_pointer, basis_frame))
        self.results.append(result)
        return result
