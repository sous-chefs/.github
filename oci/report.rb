# frozen_string_literal: true

require 'json'

def publication_message
  if ENV['VERIFIED'] == 'success'
    return "OCI cookbook verified: #{ENV.fetch('REFERENCE')}"
  end

  steps = JSON.parse(ENV.fetch('STEP_RESULTS', '{}'))
  failures = steps.filter_map do |name, result|
    outcome = result['outcome']
    "#{name} (#{outcome})" if %w[failure cancelled].include?(outcome)
  end

  reason = failures.empty? ? 'Verification was skipped or not reached.' : failures.join(', ')
  "OCI publication incomplete (non-blocking). #{reason}"
end

def append_summary(message)
  directory = ENV.fetch('OCI_WORK') { File.join(ENV.fetch('RUNNER_TEMP'), 'cookbook-oci') }
  state_path = File.join(directory, 'state.json')

  File.open(ENV.fetch('GITHUB_STEP_SUMMARY'), 'a') do |summary|
    summary.puts message
    if File.file?(state_path)
      JSON.parse(File.read(state_path)).each do |key, value|
        summary.puts "- #{key}: `#{value}`"
      end
    end
  end
end

message = publication_message
puts "::warning::#{message}" unless ENV['VERIFIED'] == 'success'
append_summary(message)
