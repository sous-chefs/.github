# frozen_string_literal: true

# Use the same loader, validation and staging implementation as knife supermarket
# share. Run only in the pinned Workstation container, without publishing secrets.
require 'chef'
require 'chef/cookbook_loader'
require 'chef/cookbook_uploader'
require 'chef/knife'
require 'chef/knife/core/cookbook_site_streaming_uploader'
require 'fileutils'
require 'json'

source, name, tag, destination = ARGV
abort 'Expected SOURCE NAME TAG DESTINATION' unless destination
abort 'Invalid cookbook name' unless name.match?(/\A[a-z0-9_][a-z0-9_-]*\z/)
loader = Chef::CookbookLoader.new(File.dirname(File.expand_path(source)))
cookbook = loader[name]
abort 'Cookbook metadata name does not match repository name' unless cookbook.name.to_s == name
version = cookbook.metadata.version.to_s
abort 'Release tag does not match cookbook version' unless [version, "v#{version}"].include?(tag)
Chef::CookbookUploader.new(cookbook, rest: Object.new).validate_cookbooks
staged = Chef::Knife::Core::CookbookSiteStreamingUploader.create_build_dir(cookbook)
begin
  FileUtils.mkdir_p(destination)
  FileUtils.cp_r(File.join(staged, name), destination)
ensure
  FileUtils.remove_entry(staged)
end
