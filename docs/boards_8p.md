# Secret Hitler - 8 Player Game Boards

## Team Composition (8 Players)

| Role            | Count |
|-----------------|-------|
| Liberals        | 5     |
| Fascists        | 2     |
| Hitler          | 1     |

**Night Phase (8 players):** Fascists open their eyes and see each other. Hitler keeps eyes closed but extends a thumbs-up. Fascists identify Hitler, but **Hitler does NOT know who the Fascists are**.

---

## Fascist Board (7-8 Players)

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                                  F A S C I S T                                     ║
╠══════════════╦══════════════╦══════════════╦══════════════╦══════════════╦══════════╣
║              ║              ║              ║              ║              ║          ║
║      1       ║      2       ║      3       ║      4       ║      5       ║    6     ║
║              ║              ║              ║              ║              ║          ║
║   [     ]    ║   [     ]    ║   [     ]    ║   [     ]    ║   [     ]    ║  [SKULL] ║
║              ║              ║              ║              ║              ║          ║
║  (no power)  ║ Investigate  ║   Special    ║  Execution   ║  Execution   ║ FASCIST  ║
║              ║   Loyalty    ║  Election    ║              ║   + VETO     ║ VICTORY  ║
║              ║              ║              ║              ║   UNLOCKED   ║          ║
╚══════════════╩══════════════╩══════════════╩══════════════╩══════════════╩══════════╝
```

### Presidential Powers (triggered when a Fascist Policy fills that slot)

| Slot | Power               | Description |
|------|---------------------|-------------|
| 1    | _(none)_            | No executive action. |
| 2    | Investigate Loyalty | The President chooses a player to investigate. That player hands over their **Party Membership card** (not Secret Role). The President sees it in secret, returns it, and may share or lie about the result. A player may not be investigated twice. |
| 3    | Call Special Election | The President chooses any other player to be the next Presidential Candidate. After the Special Election resolves, the presidency returns to the left of the President who called the Special Election. |
| 4    | Execution           | The President formally executes a player. If that player is Hitler, **Liberals win immediately**. The executed player's role is NOT revealed. Dead players may not speak, vote, or hold office. |
| 5    | Execution + Veto    | Same as above. Additionally, **Veto Power is permanently unlocked** for all future Legislative Sessions. |
| 6    | _(game over)_       | If six Fascist Policies are enacted, **Fascists win immediately**. |

### Veto Power (unlocked after 5th Fascist Policy)

Once unlocked, during any Legislative Session the Chancellor may say **"I wish to veto this agenda."** If the President agrees by saying **"I agree to the veto,"** all three policies are discarded and no policy is enacted. The Election Tracker advances by one. If the President does not consent, the Chancellor must enact a policy as normal.

---

## Liberal Board

```
╔═══════════╦══════════════════════════════════════════════════════════════╦═══════════╗
║           ║                        L I B E R A L                       ║           ║
║   DRAW    ╠════════════╦════════════╦════════════╦════════════╦════════╣  DISCARD  ║
║   PILE    ║            ║            ║            ║            ║        ║   PILE    ║
║           ║     1      ║     2      ║     3      ║     4      ║   5    ║           ║
║    ___    ║            ║            ║            ║            ║        ║    ___    ║
║   |   |   ║  [     ]   ║  [     ]   ║  [     ]   ║  [     ]   ║ [   ]  ║   |   |   ║
║   |___|   ║            ║            ║            ║            ║        ║   |___|   ║
║           ╠════════════╩════════════╩════════════╩════════════╩════════╣           ║
║           ║  ELECTION TRACKER:                                        ║           ║
║           ║    [ FAIL ] --> [ FAIL ] --> [ FAIL ] --> TOP POLICY       ║           ║
║           ║                                          ENACTED          ║           ║
╚═══════════╩══════════════════════════════════════════════════════════════╩═══════════╝
```

- **No presidential powers** on the Liberal board.
- Enacting **5 Liberal Policies** = **Liberals win immediately**.

### Election Tracker

| Fails | Effect |
|-------|--------|
| 1     | Tracker advances. |
| 2     | Tracker advances. |
| 3     | **Country is in chaos.** The top policy from the draw pile is immediately revealed and enacted. No presidential power is granted. The tracker resets. All term limits are cleared. |

If fewer than 3 tiles remain in the Policy deck at this point, shuffle the discard pile back in to form a new deck.

---

## Policy Deck

| Type    | Count |
|---------|-------|
| Liberal | 6     |
| Fascist | 11    |
| **Total** | **17** |

---

## Win Conditions

### Liberals Win
- Enact **5 Liberal Policies**, OR
- **Assassinate Hitler** (via the Execution presidential power)

### Fascists Win
- Enact **6 Fascist Policies**, OR
- **Elect Hitler as Chancellor** after 3 or more Fascist Policies have been enacted

---

## Key Rules Reference

### Election
1. **Presidential Candidacy** passes clockwise each round.
2. **President nominates a Chancellor.** The last elected President and last elected Chancellor are term-limited (ineligible for Chancellor).
3. **All players vote** (Ja!/Nein) simultaneously. Majority Ja! = government is elected. Tie or majority Nein = government fails, election tracker advances.

### Legislative Session
1. President draws **3 policy tiles** in secret.
2. President **discards 1**, passes remaining **2 to the Chancellor**.
3. Chancellor **discards 1**, enacts the remaining **1 policy** face-up on the appropriate board.
4. **No communication** between President and Chancellor during this process.
5. Both may **lie** about what they drew/received afterward.

### Post-Legislation
- If fewer than 3 tiles remain in the draw pile, shuffle the discard pile back in.
- If a Fascist Policy triggers a Presidential Power, the President **must** use it before the next round.
- If a Liberal Policy is enacted (or a powerless Fascist slot), proceed directly to the next Election.

### Hitler Chancellor Check
- After **3+ Fascist Policies** are enacted, if a newly elected Chancellor **is Hitler**, the Fascists win immediately. If not, all players now know that Chancellor is **not** Hitler.
