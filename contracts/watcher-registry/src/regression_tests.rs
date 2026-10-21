use super::*;
use soroban_sdk::{
    testutils::{Address as _, Events as _},
    Address, Env, FromVal,
};

fn setup() -> (Env, Address, WatcherRegistryClient<'static>) {
    let env = Env::default();
    env.mock_all_auths();
    let contract_id = env.register(WatcherRegistry, ());
    let client = WatcherRegistryClient::new(&env, &contract_id);
    let admin = Address::generate(&env);
    client.initialize(&admin);
    (env, admin, client)
}

/// Regression test for historical bug:
/// `replace_watcher could drop the replacement watcher.`
///
/// Ensures that when replacing `old_watcher` with `new_watcher`, the `new_watcher`
/// is successfully added and authorized, rather than being dropped from the registry.
#[test]
fn test_regression_replace_watcher_dropping_replacement() {
    let (env, admin, client) = setup();
    let old_watcher = Address::generate(&env);
    let new_watcher = Address::generate(&env);

    client.register_watcher(&admin, &old_watcher);
    assert!(client.is_watcher_authorized(&old_watcher));
    assert!(!client.is_watcher_authorized(&new_watcher));

    // Replace old with new
    assert_eq!(
        client
            .try_replace_watcher(&admin, &old_watcher, &new_watcher)
            .unwrap(),
        Ok(())
    );

    // Verify old is removed and replacement is NOT dropped
    assert!(!client.is_watcher_authorized(&old_watcher));
    assert!(client.is_watcher_authorized(&new_watcher));

    let list = client.get_watchers();
    assert_eq!(list.len(), 1);
    assert_eq!(list.get(0).unwrap(), new_watcher);
    assert_eq!(client.get_watcher_count(), 1);
}

/// Regression test for historical bug:
/// `decrement_watcher_count never being called` / `get_watcher_count now decrements correctly on removal.`
///
/// Ensures that `remove_watcher` correctly decrements the active watcher count
/// instead of monotonically increasing or failing to decrement.
#[test]
fn test_regression_decrement_watcher_count_never_being_called() {
    let (env, admin, client) = setup();
    let w1 = Address::generate(&env);
    let w2 = Address::generate(&env);
    let w3 = Address::generate(&env);

    client.register_watcher(&admin, &w1);
    client.register_watcher(&admin, &w2);
    client.register_watcher(&admin, &w3);
    assert_eq!(client.get_watcher_count(), 3);

    client.remove_watcher(&admin, &w2);
    assert_eq!(client.get_watcher_count(), 2);

    client.remove_watcher(&admin, &w1);
    assert_eq!(client.get_watcher_count(), 1);

    client.remove_watcher(&admin, &w3);
    assert_eq!(client.get_watcher_count(), 0);
}

/// Regression test for historical bug:
/// `WatcherRegistry::remove_watcher no longer emits an event when the watcher address was not registered.`
///
/// Ensures that attempting to remove an unregistered address succeeds silently (no-op)
/// and does not emit any `("watcher", "remove")` event.
#[test]
fn test_regression_remove_watcher_unregistered_emits_no_event() {
    let (env, admin, client) = setup();
    let unregistered = Address::generate(&env);

    // Removing an unregistered watcher should be a silent no-op
    assert_eq!(
        client.try_remove_watcher(&admin, &unregistered).unwrap(),
        Ok(())
    );

    let events = env.events().all();
    assert_eq!(
        events.len(),
        0,
        "No event should be emitted when removing an unregistered watcher"
    );
}

/// Regression test for historical bug:
/// `clear_all_watchers emits one event per removed watcher.`
///
/// Ensures that clearing all watchers emits individual `("watcher", "remove")`
/// events for all removed addresses so off-chain systems immediately revoke trust.
#[test]
fn test_regression_clear_all_watchers_emits_one_event_per_removed_watcher() {
    let (env, admin, client) = setup();
    let w1 = Address::generate(&env);
    let w2 = Address::generate(&env);

    client.register_watcher(&admin, &w1);
    client.register_watcher(&admin, &w2);
    assert_eq!(client.get_watcher_count(), 2);

    client.clear_all_watchers(&admin);

    let events = env.events().all();
    let mut removed = 0;
    for i in 0..events.len() {
        let (_, topics, data) = events.get(i).unwrap();
        if topics.len() == 2
            && soroban_sdk::Symbol::from_val(&env, &topics.get(0).unwrap())
                == soroban_sdk::symbol_short!("watcher")
            && soroban_sdk::Symbol::from_val(&env, &topics.get(1).unwrap())
                == soroban_sdk::symbol_short!("remove")
        {
            let (emitted_addr,): (Address,) = soroban_sdk::FromVal::from_val(&env, &data);
            assert!(emitted_addr == w1 || emitted_addr == w2);
            removed += 1;
        }
    }
    assert_eq!(removed, 2);

    assert_eq!(client.get_watcher_count(), 0);
    assert_eq!(client.get_watchers().len(), 0);
}

/// Regression test for historical bug:
/// `remove_admin refusing to remove the last admin to prevent permanent lockout.`
///
/// Ensures that attempting to remove the sole admin returns `ContractError::LastAdmin`.
#[test]
fn test_regression_remove_last_admin_lockout() {
    let (_env, admin, client) = setup();

    let res = client.try_remove_admin(&admin, &admin);
    assert_eq!(
        res.unwrap_err().unwrap(),
        ContractError::LastAdmin,
        "Removing the sole admin must return LastAdmin error"
    );
    assert_eq!(client.get_admins().len(), 1);
}

/// Regression test for #380:
/// Redundant `pause` (when already paused) and `unpause` (when already running)
/// calls are silent no-ops that do not emit duplicate `admin.pause` or
/// `admin.unpause` events.
#[test]
fn test_regression_pause_and_unpause_redundant_transitions_are_noops() {
    let (env, admin, client) = setup();

    client.unpause(&admin);
    assert!(!client.is_paused());
    assert!(env.events().all().is_empty());

    client.pause(&admin);
    assert!(client.is_paused());
    assert_eq!(env.events().all().len(), 1);

    client.pause(&admin);
    assert!(client.is_paused());
    assert!(env.events().all().is_empty());

    client.unpause(&admin);
    assert!(!client.is_paused());
    assert_eq!(env.events().all().len(), 1);

    client.unpause(&admin);
    assert!(!client.is_paused());
    assert!(env.events().all().is_empty());
/// Regression test for #370: an admin transfer proposal cannot be accepted
/// after `ADMIN_TRANSFER_EXPIRY_LEDGERS`.
#[test]
fn test_regression_admin_transfer_proposal_expires() {
    use soroban_sdk::testutils::Ledger as _;

    let (env, admin, client) = setup();
    let new_admin = Address::generate(&env);
    client.propose_admin_transfer(&admin, &new_admin);

    // One ledger past the expiry ledger.
    env.ledger()
        .with_mut(|li| li.sequence_number += ADMIN_TRANSFER_EXPIRY_LEDGERS + 1);
    assert_eq!(
        client
            .try_accept_admin_transfer(&new_admin)
            .unwrap_err()
            .unwrap(),
        ContractError::AdminTransferExpired
    );

    // A fresh proposal replaces the expired one and can be accepted.
    client.propose_admin_transfer(&admin, &new_admin);
    client.accept_admin_transfer(&new_admin);
    assert!(client.is_admin(&new_admin));
}
