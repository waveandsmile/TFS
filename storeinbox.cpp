// Copyright 2022 The Forgotten Server Authors. All rights reserved.
// Use of this source code is governed by the GPL-2.0 License that can be found in the LICENSE file.

#include "otpch.h"

#include "storeinbox.h"
#include "player.h"

StoreInbox::StoreInbox(uint16_t type) : Container(type, 5, true, true) {}

ReturnValue StoreInbox::queryAdd(int32_t, const Thing& thing, uint32_t, uint32_t flags, Creature*) const
{
	const Item* item = thing.getItem();
	if (!item) {
		return RETURNVALUE_NOTPOSSIBLE;
	}

	if (item == this) {
		return RETURNVALUE_THISISIMPOSSIBLE;
	}

	if (!item->isPickupable()) {
		return RETURNVALUE_CANNOTPICKUP;
	}

	if (!hasBitSet(FLAG_NOLIMIT, flags)) {
		if (!item->isStoreItem()) {
			return RETURNVALUE_CANNOTMOVEITEMISNOTSTOREITEM;
		}
	}

	return RETURNVALUE_NOERROR;
}

void StoreInbox::postAddNotification(Thing* thing, const Cylinder* oldParent, int32_t index, cylinderlink_t)
{
	if (parent != nullptr) {
		// A charm placed in the charm container grants its rarity abilities to the owner.
		if (Creature* creature = parent->getCreature()) {
			if (Player* player = creature->getPlayer()) {
				player->applyStoreInboxAbilities(thing->getItem(), true);
			}
		}
		parent->postAddNotification(thing, oldParent, index, LINK_TOPPARENT);
	}
}

void StoreInbox::postRemoveNotification(Thing* thing, const Cylinder* newParent, int32_t index, cylinderlink_t)
{
	if (parent != nullptr) {
		// Taking a charm out of the charm container removes the abilities it granted.
		if (Creature* creature = parent->getCreature()) {
			if (Player* player = creature->getPlayer()) {
				player->applyStoreInboxAbilities(thing->getItem(), false);
			}
		}
		parent->postRemoveNotification(thing, newParent, index, LINK_TOPPARENT);
	}
}

