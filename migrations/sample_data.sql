-- Insert Users
INSERT INTO `user` (`id`, `discord_id`, `access_token`, `created_at`, `updated_at`, `username`, `is_active`, `permission`)
VALUES
  (1, 123456789012345678, 'token1', NOW(), NOW(), 'alice', TRUE, 0),
  (2, 987654321098765432, 'token2', NOW(), NOW(), 'bob', TRUE, 1),
  (3, 192837465564738291, 'token3', NOW(), NOW(), 'charlie', TRUE, 2);

-- Insert Tournaments
INSERT INTO `tournament` (`id`, `name`, `created_at`, `updated_at`)
VALUES
  (1, 'Spring Cup', NOW(), NOW()),
  (2, 'Autumn Showdown', NOW(), NOW());

-- Insert StreamRooms
INSERT INTO `streamroom` (`id`, `name`, `stream_url`, `is_active`, `created_at`, `updated_at`)
VALUES
  (1, 'Main Room', 'https://twitch.tv/mainroom', TRUE, NOW(), NOW()),
  (2, 'Backup Room', 'https://twitch.tv/backuproom', TRUE, NOW(), NOW());

-- Insert Matches
INSERT INTO `match` (`id`, `tournament_id`, `stream_room_id`, `player_count`, `player1_id`, `player2_id`, `player3_id`, `player4_id`, `score1`, `score2`, `scheduled_at`, `created_at`, `updated_at`)
VALUES
  (1, 1, 1, 2, 1, 2, NULL, NULL, 1, 2, NOW(), NOW(), NOW()),
  (2, 2, 2, 4, 1, 2, 3, NULL, NULL, NULL, NOW(), NOW(), NOW());

-- Insert MatchConfirmations
INSERT INTO `matchconfirmations` (`id`, `match_id`, `user_id`, `confirmed`, `created_at`, `updated_at`)
VALUES
  (1, 1, 1, TRUE, NOW(), NOW()),
  (2, 1, 2, FALSE, NOW(), NOW());

-- Insert Commentators
INSERT INTO `commentator` (`id`, `user_id`, `match_id`, `approved`, `approved_by_id`, `created_at`, `updated_at`)
VALUES
  (1, 3, 1, TRUE, 2, NOW(), NOW());

-- Insert Trackers
INSERT INTO `tracker` (`id`, `user_id`, `match_id`, `approved`, `approved_by_id`, `created_at`, `updated_at`)
VALUES
  (1, 2, 1, TRUE, 1, NOW(), NOW());

-- Insert AuditLogs
INSERT INTO `auditlog` (`id`, `user_id`, `action`, `details`, `created_at`)
VALUES
  (1, 1, 'Created match', 'Match 1 created by Alice', NOW()),
  (2, 2, 'Confirmed match', 'Bob confirmed match 1', NOW());

-- Insert TestModel
INSERT INTO `testmodel` (`id`, `name`, `description`, `value`, `somethingelse`, `created_at`, `updated_at`)
VALUES
  (1, 'Test1', 'First test model', 42, 'Extra info', NOW(), NOW()),
  (2, 'Test2', 'Second test model', 99, 'More info', NOW(), NOW());