INSERT INTO commands (name, description, python_code) VALUES
(
    'echo',
    'Print the message on the agent and return the input message',
    'print(message); return message'
),
(
    'add2',
    'Add two integers together and return the result',
    'return a + b'
),
(
    'timer_seconds',
    'Wait certain amount of seconds',
    'import time
for i in range(abs(sec_count)):
    print(f"Second counter: {i+1}"); time.sleep(1)
return f"Successfully waited for {abs(sec_count)} seconds"'
),
(
    'dissalowed_command',
    'This command will always result in ImportError',
    'import os
pass
return f"This will never be returned"'
);

INSERT INTO command_parameters (command_id, name, param_type, is_required, default_value, description)
VALUES
((SELECT id FROM commands WHERE name = 'echo'), 'message', 'text', TRUE, NULL, 'Message to echo back'),
((SELECT id FROM commands WHERE name = 'add2'), 'a', 'integer', TRUE, NULL, 'First number to add'),
((SELECT id FROM commands WHERE name = 'add2'), 'b', 'integer', FALSE, 2, 'Second number to add'),
((SELECT id FROM commands WHERE name = 'timer_seconds'), 'sec_count', 'integer', TRUE, NULL, 'Amount of seconds to wait');
