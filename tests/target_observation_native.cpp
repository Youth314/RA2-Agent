// Offline policy only: no YR memory, ABI calls or game input.
#include "target_observation.hpp"
#include <cassert>
#include <cstdlib>
#include <iostream>

using namespace ra2::target_observation;

int main(int argc, char** argv) {
  assert(argc == 2);
  const int test = std::atoi(argv[1]);
  constexpr std::uint32_t player = 0x1000;
  Member actor{0xA1, 1043800, player, 15, true, false, 0xB1};
  Member target{0xB1, 1043823, player, 1, true, false, 0};
  Members members{{actor.pointer, actor}, {target.pointer, target}};
  if (test == 1) {
    assert(resolve(actor, player, members).status == Status::object);
    actor.target = 0;
    assert(resolve(actor, player, members).status == Status::none);
    actor.target = 0xDEADBEEF;
    auto unknown = resolve(actor, player, members);
    assert(unknown.status == Status::unobservable && !unknown.target);
    // Losing a member must not leave a reference to the preceding snapshot.
    actor.target = target.pointer;
    members.erase(target.pointer);
    assert(resolve(actor, player, members).status == Status::unobservable);
  } else if (test == 2) {
    for (auto type : {1, 2, 6, 15}) {
      actor.object_type = type;
      members.at(target.pointer).object_type = type;
      assert(resolve(actor, player, members).status == Status::object);
    }
    for (auto type : {0, 11, 52, 99}) {
      actor.object_type = 1;
      members.at(target.pointer).object_type = type;
      assert(resolve(actor, player, members).status == Status::unobservable);
      actor.object_type = type;
      assert(resolve(actor, player, members).status == Status::not_provided);
    }
  } else if (test == 3) {
    actor.house = 0x2000;
    assert(resolve(actor, player, members).status == Status::not_provided);
    actor.house = player;
    actor.eligible = false;
    actor.target = 0;
    assert(resolve(actor, player, members).status == Status::not_provided);
    actor.eligible = true;
    assert(resolve(actor, 0, members).status == Status::not_provided);
    actor.target = target.pointer;
    members.at(target.pointer).eligible = false;
    assert(resolve(actor, player, members).status == Status::unobservable);
  } else if (test == 4) {
    auto& foreign = members.at(target.pointer);
    foreign.house = 0x2000;
    assert(resolve(actor, player, members).status == Status::unobservable);
    foreign.foreign_visible = true;
    assert(resolve(actor, player, members).status == Status::object);
    foreign.foreign_visible = false;
    assert(resolve(actor, player, members).status == Status::unobservable);
    foreign.house = player;
    assert(resolve(actor, player, members).status == Status::object);
    foreign.native_id = 0xFFFFFFFF;
    assert(resolve(actor, player, members).target->native_id == 0xFFFFFFFF);
  } else if (test == 5) {
    assert(foreign_visible(true, false, false, 0, false));
    assert(!foreign_visible(false, false, false, 0, false));
    assert(!foreign_visible(true, true, false, 0, false));
    assert(!foreign_visible(true, false, true, 0, false));
    assert(!foreign_visible(true, false, false, 0, true));
    for (int cloak : {-1, 1, 2, 3, 99}) {
      assert(!foreign_visible(true, false, false, cloak, false));
    }
  } else {
    return 2;
  }
  std::cout << "passed\n";
}
