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
);

INSERT INTO command_parameters (command_id, name, param_type, is_required, default_value, description)
VALUES
((SELECT id FROM commands WHERE name = 'echo'), 'message', 'text', TRUE, NULL, 'Message to echo back'),
((SELECT id FROM commands WHERE name = 'add2'), 'a', 'integer', TRUE, NULL, 'First number to add'),
((SELECT id FROM commands WHERE name = 'add2'), 'b', 'integer', FALSE, 2, 'Second number to add');
