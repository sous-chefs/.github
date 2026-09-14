# frozen_string_literal: true

require 'chef'
require 'chef/cookbook_loader'
require 'chef/cookbook_uploader'

path, name, version = ARGV
cookbook = Chef::CookbookLoader.new(path)[name]
abort 'Retrieved cookbook version mismatch' unless cookbook.metadata.version.to_s == version
Chef::CookbookUploader.new(cookbook, rest: Object.new).validate_cookbooks
puts "Retrieved cookbook loads successfully: #{name} #{version}"
