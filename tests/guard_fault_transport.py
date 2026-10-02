"""Test-only Guard transport faults, after normal Executor validation."""
from ra2agent.constants import NS, UnitAction
from ra2agent.engine import payloads
from ra2agent.engine.proto import fmap, pb_bytes, pb_uint
from ra2agent.engine.state import Coordinates


FAULT_ERRORS = {
    "wrong_native_id": "guard actor absent, changed or unsupported",
    "wrong_house": "guard player context changed",
    "stale_basis": "guard basis frame is stale",
    "future_basis": "guard basis frame is stale",
    "current_with_coordinates": "guard target shape mismatch",
    "position_without_coordinates": "guard target shape mismatch",
    "object_target": "guard does not accept an object target",
    "negative_coordinates": "guard coordinates out of range",
    "outside_map": "guard cell outside map bounds",
    "unknown_actor": "guard actor absent, changed or unsupported",
    "foreign_actor": "guard actor absent, changed or unsupported",
    "infantry_actor": "guard actor absent, changed or unsupported",
}


def fault_request(body, fault, *, other_house=None,
                  foreign_pointer=None, foreign_native_id=None,
                  infantry_pointer=None, infantry_native_id=None):
    """Alter one fixed, single-actor GuardCurrent request; never accept arbitrary actions."""
    if fault not in FAULT_ERRORS:
        raise ValueError("Unknown Guard test fault")
    fields = fmap(body)
    if (set(fields) != {1, 2, 5, 6, 7}
            or any(len(items) != 1 or items[0][0] != 0 for items in fields.values())
            or fields[2][0][1] != UnitAction.GUARD_CURRENT):
        raise ValueError("Fault baseline must be a single GuardCurrent request")
    values = {n: items[0][1] for n, items in fields.items()}
    extra = b""

    def positive(value):
        if type(value) is not int or not 0 < value <= 0xFFFFFFFF:
            raise ValueError("Missing nonzero uint32 test identity")
        return value

    if fault == "wrong_native_id":
        values[5] = values[5] % 0xFFFFFFFF + 1
    elif fault == "wrong_house":
        values[6] = positive(other_house)
        if values[6] == fields[6][0][1]:
            raise ValueError("House fault must differ from the actual owner")
    elif fault == "stale_basis":
        if values[7] <= 150:
            raise ValueError("Stale test needs current frame greater than 150")
        values[7] = 0
    elif fault == "future_basis":
        if values[7] > 0xFFFFFFFF - 100000:
            raise ValueError("Future frame would overflow")
        values[7] += 100000
    elif fault == "current_with_coordinates":
        extra = pb_bytes(4, payloads.coordinates_payload(Coordinates(128, 128, 0)))
    elif fault == "position_without_coordinates":
        values[2] = int(UnitAction.GUARD_POSITION)
    elif fault == "object_target":
        extra = pb_uint(3, values[1])
    elif fault in ("negative_coordinates", "outside_map"):
        values[2] = int(UnitAction.GUARD_POSITION)
        point = (Coordinates(-1, 128, 0) if fault == "negative_coordinates"
                 else Coordinates(511 * 256 + 128, 511 * 256 + 128, 0))
        extra = pb_bytes(4, payloads.coordinates_payload(point))
    elif fault == "unknown_actor":
        values[1] = 1  # Cannot equal an aligned live Techno pointer; DLL scans membership first.
    elif fault == "foreign_actor":
        values[1] = positive(foreign_pointer)
        values[5] = positive(foreign_native_id)
    elif fault == "infantry_actor":
        values[1] = positive(infantry_pointer)
        values[5] = positive(infantry_native_id)
    return b"".join(pb_uint(n, v) for n, v in sorted(values.items())) + extra


class GuardFaultTransport:
    """Private Executor client adapter; arm once, record real replies, no retries."""

    def __init__(self, client):
        self.client = client
        self.armed = None
        self.requests = []
        self.results = []

    def __getattr__(self, name):
        return getattr(self.client, name)

    def arm(self, fault, **identities):
        if fault not in FAULT_ERRORS or self.armed is not None:
            raise ValueError("Unknown fault or a fault is already armed")
        self.armed = (fault, identities)

    def guard_order(self, pointer, action, native_id, house_pointer, basis_frame,
                    coordinates=None):
        original = payloads.guard_order(pointer, action, native_id, house_pointer,
                                        basis_frame, coordinates)
        armed, self.armed = self.armed, None
        body = fault_request(original, armed[0], **armed[1]) if armed else original
        self.requests.append({"fault": armed[0] if armed else None,
                              "valid_request_hex": original.hex(), "request_hex": body.hex()})
        if armed:
            result = self.client.send_command(NS + "UnitOrder", body)
        else:
            result = self.client.guard_order(pointer, action, native_id, house_pointer,
                                             basis_frame, coordinates)
        self.results.append(result)
        return result
