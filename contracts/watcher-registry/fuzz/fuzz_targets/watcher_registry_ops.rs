#![no_main]

//! Stateful fuzz harness for `WatcherRegistry`.
//!
//! Applies a fuzzer-controlled sequence of admin/watcher operations and asserts
//! the following invariants after every step:
//!
//! 1. `W_CNT == len(get_watchers())` — the stored counter stays in sync with the list.
//! 2. `len(get_admins()) >= 1` — there is always at least one admin.
//! 3. No duplicate addresses in the watcher set.
//! 4. No duplicate addresses in the admin set.

use arbitrary::Arbitrary;
use libfuzzer_sys::fuzz_target;
use soroban_sdk::{testutils::Address as _, Address, Env};
use watcher_registry::{WatcherRegistry, WatcherRegistryClient};

// ── Operation vocabulary ──────────────────────────────────────────────────────

/// Each variant encodes indices into the shared address pool so the fuzzer
/// only needs to emit small integers, not full 32-byte addresses.
#[derive(Arbitrary, Debug)]
enum Op {
    RegisterWatcher  { admin_idx: u8, watcher_idx: u8 },
    RemoveWatcher    { admin_idx: u8, watcher_idx: u8 },
    ReplaceWatcher   { admin_idx: u8, old_idx: u8, new_idx: u8 },
    AddAdmin         { caller_idx: u8, new_admin_idx: u8 },
    RemoveAdmin      { caller_idx: u8, target_idx: u8 },
    ClearAllWatchers { admin_idx: u8 },
}

// ── Structured fuzz input ─────────────────────────────────────────────────────

#[derive(Arbitrary, Debug)]
struct FuzzInput {
    /// Pool size is kept between 2 and 16 via modular reduction in the harness.
    pool_size: u8,
    /// The sequence of operations to apply.
    ops: Vec<Op>,
}

// ── Harness ───────────────────────────────────────────────────────────────────

fuzz_target!(|input: FuzzInput| {
    // Pool of 2-16 addresses; keeps indices meaningful without blowing the budget.
    let pool_size = (input.pool_size as usize % 15) + 2;

    let env = Env::default();
    env.mock_all_auths();

    // Build a stable address pool for this run.
    let pool: Vec<Address> = (0..pool_size)
        .map(|_| Address::generate(&env))
        .collect();

    // Resolve a fuzz-controlled index to a pooled address.
    let addr = |idx: u8| -> Address { pool[idx as usize % pool_size].clone() };

    // Deploy contract with pool[0] as the bootstrap admin via __constructor.
    let contract_id = env.register(WatcherRegistry, (pool[0].clone(),));
    let client = WatcherRegistryClient::new(&env, &contract_id);

    for op in &input.ops {
        // All documented error variants are acceptable outcomes; only panics
        // (host-level InvokeError) would indicate a contract bug.
        let _ = match op {
            Op::RegisterWatcher { admin_idx, watcher_idx } =>
                client.try_register_watcher(&addr(*admin_idx), &addr(*watcher_idx)),

            Op::RemoveWatcher { admin_idx, watcher_idx } =>
                client.try_remove_watcher(&addr(*admin_idx), &addr(*watcher_idx)),

            Op::ReplaceWatcher { admin_idx, old_idx, new_idx } =>
                client.try_replace_watcher(
                    &addr(*admin_idx),
                    &addr(*old_idx),
                    &addr(*new_idx),
                ),

            Op::AddAdmin { caller_idx, new_admin_idx } =>
                client.try_add_admin(&addr(*caller_idx), &addr(*new_admin_idx)),

            Op::RemoveAdmin { caller_idx, target_idx } =>
                client.try_remove_admin(&addr(*caller_idx), &addr(*target_idx)),

            Op::ClearAllWatchers { admin_idx } =>
                client.try_clear_all_watchers(&addr(*admin_idx)),
        };

        // ── Invariant checks ─────────────────────────────────────────────────

        let watchers = client.get_watchers();
        let w_cnt    = client.get_watcher_count();

        // 1. W_CNT counter must equal the actual watcher list length.
        assert_eq!(
            w_cnt,
            watchers.len(),
            "W_CNT ({w_cnt}) != len(watchers) ({}): counter is out of sync",
            watchers.len(),
        );

        // get_admins returns Result; the contract is always initialized here
        // so Err(NotInitialized) is impossible — unwrap is safe.
        let admins = client.get_admins().expect("get_admins must not fail on initialized contract");

        // 2. Admin set must never be empty (LastAdmin guard).
        assert!(
            admins.len() >= 1,
            "admin set is empty — contract would be permanently locked"
        );

        // 3. No duplicate watchers.
        let watcher_vec: Vec<Address> = (0..watchers.len())
            .map(|i| watchers.get(i).unwrap())
            .collect();
        for i in 0..watcher_vec.len() {
            for j in (i + 1)..watcher_vec.len() {
                assert_ne!(
                    watcher_vec[i], watcher_vec[j],
                    "duplicate watcher found at indices {i} and {j}"
                );
            }
        }

        // 4. No duplicate admins.
        let admin_vec: Vec<Address> = (0..admins.len())
            .map(|i| admins.get(i).unwrap())
            .collect();
        for i in 0..admin_vec.len() {
            for j in (i + 1)..admin_vec.len() {
                assert_ne!(
                    admin_vec[i], admin_vec[j],
                    "duplicate admin found at indices {i} and {j}"
                );
            }
        }
    }
});
