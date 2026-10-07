// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "LWebSocketServerWrapper.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnWsServerClientConnectedEvent, const FString&, ClientId);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnWsServerClientDisconnectedEvent, const FString&, ClientId, int32, StatusCode);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnWsServerMessageEvent, const FString&, ClientId, const FString&, Message);

UCLASS(BlueprintType, Blueprintable)
class UE5PROJECT_API ULWebSocketServerWrapper : public UObject
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category = "WebSocket")
	bool Start(int32 Port);

	UFUNCTION(BlueprintCallable, Category = "WebSocket")
	static void Stop();

	UFUNCTION(BlueprintCallable, Category = "WebSocket")
	static bool Broadcast(const FString& Message);

	UFUNCTION(BlueprintCallable, Category = "WebSocket")
	static bool SendToClient(const FString& ClientId, const FString& Message);

	UFUNCTION(BlueprintCallable, Category = "WebSocket")
	static bool IsRunning();

	UPROPERTY(BlueprintAssignable, Category = "WebSocket")
	FOnWsServerClientConnectedEvent OnClientConnectedEvent;

	UPROPERTY(BlueprintAssignable, Category = "WebSocket")
	FOnWsServerClientDisconnectedEvent OnClientDisconnectedEvent;

	UPROPERTY(BlueprintAssignable, Category = "WebSocket")
	FOnWsServerMessageEvent OnMessageEvent;

private:
	UFUNCTION()
	void HandleClientConnected(const FString& ClientId);

	UFUNCTION()
	void HandleClientDisconnected(const FString& ClientId, int32 StatusCode);

	UFUNCTION()
	void HandleMessage(const FString& ClientId, const FString& Message);
};
